import os
import time
import requests
import psycopg2
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor

resource = Resource.create({"service.name": "order-service"})
provider = TracerProvider(resource=resource)
processor = BatchSpanProcessor(OTLPSpanExporter(endpoint="http://jaeger:4318/v1/traces"))
provider.add_span_processor(processor)
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(__name__)

# Автоматична інструментація клієнтів HTTP та PostgreSQL
RequestsInstrumentor().instrument()
Psycopg2Instrumentor().instrument()

app = FastAPI()
FastAPIInstrumentor.instrument_app(app)

DB_HOST = os.getenv("DB_HOST", "postgres")
PAYMENT_SERVICE_URL = os.getenv("PAYMENT_SERVICE_URL", "http://payment-service:8082")

def get_db():
    conn = psycopg2.connect(
        host=DB_HOST,
        user="user",
        password="password",
        dbname="orders_db"
    )
    return conn

@app.on_event("startup")
def init_db():
    time.sleep(2)  # очікування готовності postgres
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id VARCHAR(50) PRIMARY KEY,
            item VARCHAR(100),
            amount NUMERIC,
            status VARCHAR(20)
        );
    """)
    conn.commit()
    cur.close()
    conn.close()

class OrderCreate(BaseModel):
    order_id: str
    item: str
    amount: float

@app.post("/orders")
def create_order(order: OrderCreate):
    with tracer.start_as_current_span("validate_inventory") as span:
        span.set_attribute("order.id", order.order_id)
        time.sleep(0.05) # валідація залишків 50ms

    # 1. Запис у базу даних (span створюється автоматично завдяки Psycopg2Instrumentor)
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO orders (id, item, amount, status) VALUES (%s, %s, %s, %s)",
        (order.order_id, order.item, order.amount, "PENDING")
    )
    conn.commit()

    # 2. Виклик міжсервісної взаємодії (payment-service) з передачею TraceContext у заголовках
    try:
        resp = requests.post(
            f"{PAYMENT_SERVICE_URL}/payments/process",
            json={"order_id": order.order_id, "amount": order.amount},
            timeout=2.0
        )
        if resp.status_code != 200:
            cur.execute("UPDATE orders SET status = %s WHERE id = %s", ("FAILED", order.order_id))
            conn.commit()
            raise HTTPException(status_code=502, detail="Payment failed upstream")
    except requests.exceptions.RequestException as e:
        cur.execute("UPDATE orders SET status = %s WHERE id = %s", ("TIMEOUT", order.order_id))
        conn.commit()
        raise HTTPException(status_code=504, detail=f"Payment service unavailable: {str(e)}")
    finally:
        cur.close()
        conn.close()

    return {"message": "Order created successfully", "order_id": order.order_id}