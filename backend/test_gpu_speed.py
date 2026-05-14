import asyncio
import time
import httpx

async def test():
    # 测试单条速度
    payload = {"model": "bge-m3", "input": ["测试一段中文文本，长度大约五十个字左右。"]}
    async with httpx.AsyncClient(timeout=60.0) as client:
        start = time.time()
        resp = await client.post("http://localhost:11434/api/embed", json=payload)
        elapsed = time.time() - start
        print(f"single status={resp.status_code}, time={elapsed:.2f}s")

    # 测试 batch 20 速度
    texts = ["汉" * 2000 for _ in range(20)]
    payload = {"model": "bge-m3", "input": texts}
    async with httpx.AsyncClient(timeout=120.0) as client:
        start = time.time()
        resp = await client.post("http://localhost:11434/api/embed", json=payload)
        elapsed = time.time() - start
        print(f"batch20 status={resp.status_code}, time={elapsed:.2f}s")
        if resp.status_code == 200:
            data = resp.json()
            print(f"  embeddings count: {len(data.get('embeddings', []))}")

asyncio.run(test())
