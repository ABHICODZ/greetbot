from fastapi import FastAPI
from pydantic import BaseModel
import brain

app = FastAPI(title="GreetBot API")


class AskRequest(BaseModel):
    text: str


class AskResponse(BaseModel):
    response: str
    emotion: str


@app.get("/")
def health():
    return {"status": "online", "bot_name": brain.CONFIG["BOT_NAME"]}


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    response_text, emotion = brain.query_ollama(req.text)
    return AskResponse(response=response_text, emotion=emotion)
