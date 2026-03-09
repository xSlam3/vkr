from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.base import Base
from app.db.session import engine
from app.api import chat, knowledge, media, onboarding, users

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Jewelry Onboarding API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.router)
app.include_router(onboarding.router)
app.include_router(knowledge.router)
app.include_router(media.router)
app.include_router(chat.router)
