from enum import Enum


class OrderStatus(str, Enum):
    NEW = "new"
    PAID = "paid"
    CANCELED = "canceled"
    ERROR = "error"


class OrderAction(str, Enum):
    PURCHASE = "purchase"
    RENEW = "renew"


class ProviderStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    ERROR = "ERROR"
