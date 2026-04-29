from sqlalchemy import Column, JSON
from sqlalchemy import Enum as SAEnum
from sqlmodel import SQLModel, Field
from datetime import datetime
from typing import Any, Optional
from datetime import date
from decimal import Decimal

from api.enums import FactCheckResult

class Status(SQLModel, table=True):
    __tablename__ = "Status"
    
    id: int = Field(default=None, primary_key=True, sa_column_kwargs={"name": "Id"})
    name: str = Field(max_length=50, sa_column_kwargs={"name": "Name"})

class PaymentStatus(SQLModel, table=True):
    __tablename__ = "PaymentStatus"
    
    id: int = Field(default=None, primary_key=True, sa_column_kwargs={"name": "Id"})
    name: str = Field(max_length=50, sa_column_kwargs={"name": "Name"})

class Auth(SQLModel, table=True):
    __tablename__ = "Auth"
    
    email: str = Field(primary_key=True, max_length=255, sa_column_kwargs={"name": "El_pastas"})
    password: str = Field(max_length=255, sa_column_kwargs={"name": "Slaptazodis"})

class User(SQLModel, table=True):
    __tablename__ = "User"
    
    id: Optional[int] = Field(default=None, primary_key=True, sa_column_kwargs={"name": "Id"})
    first_name: str = Field(max_length=255, sa_column_kwargs={"name": "Vardas"})
    last_name: str = Field(max_length=255, sa_column_kwargs={"name": "Pavarde"})
    email: str = Field(unique=True, max_length=255, sa_column_kwargs={"name": "El_pastas"})
    
    auth_email: str = Field(foreign_key="Auth.El_pastas", sa_column_kwargs={"name": "fk_Prisijungimas"})

class Subscription(SQLModel, table=True):
    __tablename__ = "Subscription"
    
    id: Optional[int] = Field(default=None, primary_key=True, sa_column_kwargs={"name": "Id"})
    start_time: date = Field(sa_column_kwargs={"name": "Pradzios_laikas"})
    renewal_time: date = Field(sa_column_kwargs={"name": "Atnaujinimo_laikas"})
    queries_performed: int = Field(sa_column_kwargs={"name": "Atliktos_uzklausos"})
    
    status_id: int = Field(foreign_key="Status.Id", sa_column_kwargs={"name": "fk_Busena"})
    user_id: int = Field(foreign_key="User.Id", sa_column_kwargs={"name": "fk_Naudotojas"})

class Plan(SQLModel, table=True):
    __tablename__ = "Plan"
    
    id: Optional[int] = Field(default=None, primary_key=True, sa_column_kwargs={"name": "Id"})
    title: str = Field(max_length=255, sa_column_kwargs={"name": "Pavadinimas"})
    price: Decimal = Field(max_digits=10, decimal_places=2, sa_column_kwargs={"name": "Kaina"})
    duration: int = Field(sa_column_kwargs={"name": "Trukme"})
    query_limit: int = Field(sa_column_kwargs={"name": "Uzklausu_limitas"})
    
    subscription_id: int = Field(foreign_key="Subscription.Id", sa_column_kwargs={"name": "fk_Prenumerata"}, unique=True)

class Payment(SQLModel, table=True):
    __tablename__ = "Payment"
    
    id: Optional[int] = Field(default=None, primary_key=True, sa_column_kwargs={"name": "Id"})
    date_performed: date = Field(sa_column_kwargs={"name": "Atlikimo_data"})
    amount_paid: Decimal = Field(max_digits=10, decimal_places=2, sa_column_kwargs={"name": "Sumoketa_suma"})
    
    status_id: int = Field(foreign_key="PaymentStatus.Id", sa_column_kwargs={"name": "fk_Statusas"})
    subscription_id: int = Field(foreign_key="Subscription.Id", sa_column_kwargs={"name": "fk_Prenumerata"})
    plan_id: int = Field(foreign_key="Plan.Id", sa_column_kwargs={"name": "fk_Paslauga"})

class Guest(SQLModel, table=True):
    __tablename__ = "Guest"
    
    id: Optional[int] = Field(default=None, primary_key=True, sa_column_kwargs={"name": "Id"})
    ip_address: str = Field(unique=True, max_length=255, sa_column_kwargs={"name": "Ip_adresas"})
    query_count: int = Field(sa_column_kwargs={"name": "Uzklausu_skaicius"})

class Query(SQLModel, table=True):
    __tablename__ = "Query"
    
    id: Optional[int] = Field(default=None, primary_key=True, sa_column_kwargs={"name": "Id"})
    claim_date: date = Field(sa_column_kwargs={"name": "Uzklausos_data"})
    claim_text: str = Field(max_length=255, sa_column_kwargs={"name": "Uzklausa_text"})
    result_json: Optional[dict[str, Any]] = Field(
        default=None,
        sa_column=Column("Atsakymas_json", JSON),
    )
    final_verdict: Optional[FactCheckResult] = Field(
        default=None,
        sa_column=Column(
            "Final_verdict",
            SAEnum(
                FactCheckResult,
                values_callable=lambda c: [m.value for m in c],
                native_enum=False,
                length=32,
            ),
            nullable=True,
        ),
    )
    
    # TODO discuss maybe we should add an agregate score for all the facts into one
    # final_score: Optional[float] = Field(default=None, sa_column_kwargs={"name": "Final_score"})

    user_id: int = Field(foreign_key="User.Id", sa_column_kwargs={"name": "fk_Naudotojas"})

class TokenBlacklist(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    token: str = Field(index=True)
    expires_at: datetime