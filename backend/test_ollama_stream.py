"""
测试 Ollama 流式响应
"""
import asyncio
from app.core.llm import get_llm_service, ChatMessage

async def main():
    llm = get_llm_service()
    print(f"Provider: {llm.provider}")
    print(f"Model: {llm.ollama_model}")
    print(f"Chat URL: {llm.ollama_chat_url}")
    
    messages = [ChatMessage(role="user", content="你好")]
    
    print("\nTesting chat_stream...")
    count = 0
    try:
        async for chunk in llm.chat_stream(messages, system_prompt="你是一个助手"):
            print(f"Chunk [{count}]: {repr(chunk)}")
            count += 1
            if count > 10:
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
