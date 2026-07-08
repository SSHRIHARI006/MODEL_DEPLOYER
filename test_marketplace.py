import requests
import string
import random
import time

BASE_URL = "http://localhost:8000/api"

def random_string(length=8):
    return ''.join(random.choices(string.ascii_lowercase, k=length))

def run_test():
    # 1. Generate a new user
    username = f"testuser_{random_string()}"
    email = f"{username}@example.com"
    password = "TestPassword123!"

    print(f"[*] Registering new user: {username} ({email})")
    resp = requests.post(f"{BASE_URL}/auth/register/", json={
        "username": username,
        "email": email,
        "password": password
    })
    if resp.status_code not in (200, 201):
        print(f"[!] Registration failed: {resp.text}")
        return

    # 2. Login to get JWT for dashboard actions
    resp = requests.post(f"{BASE_URL}/auth/login/", json={
        "email": email,
        "password": password
    })
    token = resp.json().get("access")
    headers = {"Authorization": f"Bearer {token}"}

    # 3. Add Credits
    print("[*] Depositing 100 credits into wallet...")
    requests.post(f"{BASE_URL}/wallet/deposit/", json={"amount": 100}, headers=headers)

    # 4. Generate Universal API Key
    print("[*] Generating Universal API Key...")
    resp = requests.post(f"{BASE_URL}/keys/universal/", json={"name": "test-script-key"}, headers=headers)
    api_key_data = resp.json()
    universal_key = api_key_data["key"]  # The raw key is only returned once!
    print(f"  -> Created key: {api_key_data['prefix']}...")

    # 5. Fetch all models from the Explore directory
    print("[*] Fetching all public models from Explore...")
    resp = requests.get(f"{BASE_URL}/models/explore/")
    models = resp.json().get("results", [])
    print(f"  -> Found {len(models)} models.")

    # 6. Test out all models using Python Requests and the Universal API Key!
    print("\n" + "="*50)
    print("🚀 COMMENCING MARKETPLACE INFERENCE TESTS")
    print("="*50)

    test_headers = {
        "Authorization": f"Bearer {universal_key}",
        "Content-Type": "application/json"
    }

    dummy_payload = {
        "instances": [
            [1.0, 2.0, 3.0, 4.0] # Generic tabular data or text fallback
        ]
    }

    for m in models:
        owner = m.get("owner_username", "unknown")
        model_name = m["name"]
        cost = m["cost_per_run"]
        print(f"\n[Test] @{owner}/{model_name} (Cost: {cost} credits)")
        
        start_time = time.time()
        url = f"{BASE_URL}/v1/inference/@{owner}/{model_name}/"
        
        try:
            inf_resp = requests.post(url, json=dummy_payload, headers=test_headers)
            elapsed = (time.time() - start_time) * 1000
            
            if inf_resp.status_code == 200:
                print(f"  ✅ SUCCESS ({elapsed:.0f}ms): {inf_resp.json()}")
            elif inf_resp.status_code == 402:
                print(f"  💳 INSUFFICIENT CREDITS: {inf_resp.json()}")
            else:
                # We expect 503s or 500s because the fake models don't actually exist in MinIO
                # But it proves the routing, auth, and billing checks passed!
                print(f"  ❌ BACKEND ERROR ({inf_resp.status_code}): {inf_resp.text}")
                
        except Exception as e:
            print(f"  ❌ REQUEST FAILED: {e}")

    # 7. Check final wallet balance
    resp = requests.get(f"{BASE_URL}/wallet/", headers=headers)
    try:
        balance = resp.json().get("wallet", {}).get("credit_balance", "error")
        print(f"\n[*] Final Wallet Balance: {balance} credits")
    except Exception as e:
        print(f"\n[*] Final Wallet check failed: {resp.status_code} {resp.text}")

if __name__ == "__main__":
    run_test()
