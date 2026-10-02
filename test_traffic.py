import time
import uuid
import random
import requests

URL = "http://localhost:8081/orders"

print(">>> Початок генерації тестового навантаження...")
for i in range(1, 51):
    order_id = f"ord-{uuid.uuid4().hex[:8]}"
    payload = {
        "order_id": order_id,
        "item": random.choice(["Mechanical Keyboard", "Monitor 4K", "RAM DDR5", "Mouse"]),
        "amount": round(random.uniform(20.0, 500.0), 2)
    }
    
    try:
        res = requests.post(URL, json=payload)
        print(f"[{i}/50] Запит {order_id} -> HTTP {res.status_code}")
    except Exception as err:
        print(f"[{i}/50] Помилка з'єднання: {err}")
    
    time.sleep(random.uniform(0.1, 0.3))

print(">>> Навантаження завершено! Перевірте Jaeger за адресою http://localhost:16686")