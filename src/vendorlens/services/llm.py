import httpx


LLM_URL = "http://127.0.0.1:8080/v1/chat/completions"


def generate_answer(prompt: str) -> str:
    response = httpx.post(
        LLM_URL,
        json={
            "messages": [
                {
                    "role": "user",
                    "content": f"/no_think\n{prompt}",
                }
            ],
            "max_tokens": 300,
            "temperature": 0.1,
        },
        timeout=60.0,
    )

    response.raise_for_status()

    data = response.json()

    return data["choices"][0]["message"]["content"]
