from sqlmodel import Session, SQLModel, create_engine

DATABASE_URL = "sqlite:///./agent_monopoly.db"
engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Session:
    return Session(engine)
