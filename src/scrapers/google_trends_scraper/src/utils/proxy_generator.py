import requests
import concurrent.futures
import os
from dotenv import load_dotenv, set_key

def fetch_free_proxies():
    """Fetches a list of free proxies from public APIs."""
    print("Fetching free proxies...")
    proxies = []
    
    # 1. Pubproxy API (Free tier)
    try:
        url = "http://pubproxy.com/api/proxy?limit=20&format=txt&http=true&country=US,GB,CA,DE,FR,IT,ES,BR,IN,JP,RO"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            proxies.extend(response.text.strip().split('\n'))
    except Exception as e:
        print(f"Error fetching from Pubproxy: {e}")

    # 2. Proxyscrape API (Free list)
    try:
        url = "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            proxies.extend(response.text.strip().split('\n'))
    except Exception as e:
        print(f"Error fetching from Proxyscrape: {e}")
        
    # 3. Spys.me list
    try:
        url = "https://spys.me/proxy.txt"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            for line in response.text.split('\n'):
                if ':' in line and not line.startswith('#'):
                    # Spys.me format: IP:PORT ...
                    proxies.append(line.split(' ')[0])
    except Exception as e:
        print(f"Error fetching from Spys.me: {e}")

    # Remove duplicates and clean
    proxies = list(set([p.strip() for p in proxies if p.strip()]))
    print(f"Fetched {len(proxies)} unique proxies for testing.")
    return proxies

def test_proxy(proxy):
    """Tests if a proxy is functional for Google Trends."""
    url = "https://trends.google.com/trends/api/explore?hl=en-US&tz=-120&req=%7B%22comparisonItem%22%3A%5B%7B%22keyword%22%3A%22Python%22%2C%22geo%22%3A%22US%22%2C%22time%22%3A%22today%2012-m%22%7D%5D%2C%22category%22%3A0%2C%22property%22%3A%22%22%7D"
    try:
        proxies_dict = {
            "http": f"http://{proxy}",
            "https": f"http://{proxy}"
        }
        response = requests.get(url, proxies=proxies_dict, timeout=5)
        if response.status_code == 200:
            return proxy
    except:
        pass
    return None

def generate_functional_proxies(limit=5):
    """Fetches and tests proxies, returning the first functional ones."""
    all_proxies = fetch_free_proxies()
    functional_proxies = []
    
    print(f"Testing proxies for functionality (limit={limit})...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        future_to_proxy = {executor.submit(test_proxy, p): p for p in all_proxies}
        for future in concurrent.futures.as_completed(future_to_proxy):
            proxy = future.result()
            if proxy:
                functional_proxies.append(f"http://{proxy}")
                print(f"Found functional proxy: {proxy}")
                if len(functional_proxies) >= limit:
                    break
    
    return functional_proxies

def update_env_with_proxies(proxies):
    """Updates the .env file with the found proxies."""
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
    if not os.path.exists(env_path):
        # Create it if it doesn't exist
        with open(env_path, 'w') as f:
            f.write("")
            
    proxy_string = ",".join(proxies)
    # Using set_key to update or add the variable
    # We'll do it manually to avoid dependency issues if set_key fails
    lines = []
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            lines = f.readlines()
            
    updated = False
    new_lines = []
    for line in lines:
        if line.startswith("SCRAPY_PROXIES="):
            new_lines.append(f'SCRAPY_PROXIES="{proxy_string}"\n')
            updated = True
        else:
            new_lines.append(line)
            
    if not updated:
        new_lines.append(f'SCRAPY_PROXIES="{proxy_string}"\n')
        
    with open(env_path, 'w') as f:
        f.writelines(new_lines)
    
    print(f"Updated {env_path} with {len(proxies)} proxies.")

if __name__ == "__main__":
    functional = generate_functional_proxies(limit=5)
    if functional:
        print(f"Success! Found {len(functional)} functional proxies.")
        update_env_with_proxies(functional)
    else:
        print("Could not find any functional free proxies at the moment.")
