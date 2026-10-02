import time
import random
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

resource = Resource.create({"service.name": "payment-service"})
provider = TracerProvider(resource=resource)
processor = BatchSpanProcessor(OTLPSpanExporter(endpoint="http://jaeger:4318/v1/traces"))
provider.add_span_processor(processor)
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(__name__)

app = FastAPI()
FastAPIInstrumentor.instrument_app(app)

class PaymentRequest(BaseModel):
    order_id: str
    amount: float

@app.post("/payments/process")
def process_payment(req: PaymentRequest):
    # 1. Емуляція виклику зовнішнього банківського API
    with tracer.start_as_current_span("call_external_bank_gateway") as span:
        span.set_attribute("bank.gateway", "MockBankAPI")
        span.set_attribute("payment.amount", req.amount)
        
        # Штучна затримка відповіді банку (200-500ms)
        delay = random.uniform(0.2, 0.5)
        time.sleep(delay)
        span.set_attribute("bank.latency_seconds", delay)

        # Моделювання 20% помилок шлюзу
        if random.random() < 0.2:
            span.record_exception(Exception("Bank API Gateway Timeout"))
            span.set_status(trace.StatusCode.ERROR, "Bank unavailable")
            raise HTTPException(status_code=502, detail="Bank Gateway Connection Refused")

    return {"status": "SUCCESS", "order_id": req.order_id, "fee": 1.5}