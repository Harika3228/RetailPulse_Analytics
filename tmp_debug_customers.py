from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)
resp = client.post('/auth/login', json={'email':'admin@retailpulse.com','password':'password123'})
print(resp.status_code)
print(resp.json())
token = resp.json()['access_token']
headers = {'Authorization': f'Bearer {token}'}
resp2 = client.get('/customers/analytics', headers=headers)
print(resp2.status_code)
print(resp2.text)
