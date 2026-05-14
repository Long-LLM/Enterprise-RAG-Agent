import asyncio
import time
import httpx

async def test_speed(batch_size: int):
    texts = ["汉" * 2000 for _ in range(batch_size)]
    payload = {"model": "bge-m3", "input": texts}
    async with httpx.AsyncClient(timeout=300.0) as client:
        start = time.time()
        resp = await client.post("http://localhost:11434/api/embed", json=payload)
        elapsed = time.time() - start
        print(f"Batch {batch_size}: status={resp.status_code}, time={elapsed:.1f}s")
        if resp.status_code == 200:
            data = resp.json()
            print(f"  Embeddings returned: {len(data.get('embeddings', []))}")
        else:
            print(f"  Error: {resp.text[:200]}")

async def main():
    for bs in [1, 5, 10, 20]:
        await test_speed(bs)
        print()

asyncio.run(main())
