"""
测试完整 query_stream 流程
"""
import asyncio
from app.services.rag_service import get_rag_service
from app.models.schemas import QueryRequest

async def main():
    service = get_rag_service()
    req = QueryRequest(question="你好", top_k=5, use_rerank=False, stream=True)
    
    print("Testing query_stream...")
    count = 0
    try:
        async for chunk in service.query_stream(req):
            print(f"Chunk [{count}]: {chunk[:100]}")
            count += 1
            if count > 15:
                print("... (truncated)")
                break
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    
    if count == 0:
        print("No chunks received!")
    else:
        print(f"Total chunks: {count}")

if __name__ == "__main__":
    asyncio.run(main())
