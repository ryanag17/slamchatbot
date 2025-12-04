from fastapi import FastAPI
from pydantic import BaseModel
from retriever import SlamChatBot

app = FastAPI()
bot = SlamChatBot()  # loads JSONs + initializes model

class Question(BaseModel):
    query: str

@app.post("/ask")
def ask_question(question: Question):
    answer = bot.get_answer(question.query)
    return {"answer": answer}
