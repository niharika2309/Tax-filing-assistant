from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Any

from pydantic import GetJsonSchemaHandler
from pydantic_core import CoreSchema, core_schema

CENTS = Decimal("0.01")


class Money:
    """USD amount backed by Decimal. Always rounded to cents (ROUND_HALF_UP)."""

    __slots__ = ("_amount",)

    def __init__(self, value: "Decimal | int | float | str | Money") -> None:
        if isinstance(value, Money):
            self._amount = value._amount
            return
        d = value if isinstance(value, Decimal) else Decimal(str(value))
        self._amount = d.quantize(CENTS, rounding=ROUND_HALF_UP)

    @property
    def amount(self) -> Decimal:
        return self._amount

    def __add__(self, other: "Money") -> "Money":
        return Money(self._amount + other._amount)

    def __sub__(self, other: "Money") -> "Money":
        return Money(self._amount - other._amount)

    def __mul__(self, factor: Decimal | int | float) -> "Money":
        f = factor if isinstance(factor, Decimal) else Decimal(str(factor))
        return Money(self._amount * f)

    def __lt__(self, other: "Money") -> bool:
        return self._amount < other._amount

    def __le__(self, other: "Money") -> bool:
        return self._amount <= other._amount

    def __gt__(self, other: "Money") -> bool:
        return self._amount > other._amount

    def __ge__(self, other: "Money") -> bool:
        return self._amount >= other._amount

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Money) and self._amount == other._amount

    def __hash__(self) -> int:
        return hash(self._amount)

    def __repr__(self) -> str:
        return f"Money({self._amount})"

    def __str__(self) -> str:
        return f"${self._amount:,.2f}"

    @classmethod
    def zero(cls) -> "Money":
        return cls(Decimal("0"))

    @classmethod
    def __get_pydantic_core_schema__(
        cls, _source_type: Any, _handler: Any
    ) -> CoreSchema:
        def validate(value: Any) -> "Money":
            if isinstance(value, Money):
                return value
            if isinstance(value, (int, float, str, Decimal)):
                return Money(value)
            if isinstance(value, dict) and "amount" in value:
                return Money(value["amount"])
            raise TypeError(f"Cannot coerce {type(value).__name__} to Money")

        def serialize(value: "Money") -> str:
            return str(value._amount)

        return core_schema.no_info_plain_validator_function(
            validate,
            serialization=core_schema.plain_serializer_function_ser_schema(
                serialize, return_schema=core_schema.str_schema()
            ),
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls, _schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> dict[str, Any]:
        return handler(
            core_schema.str_schema(
                pattern=r"^-?\d+(\.\d{1,2})?$",
            )
        )


MoneyField = Annotated[Money, "USD amount as a decimal string like '1234.56'"]
