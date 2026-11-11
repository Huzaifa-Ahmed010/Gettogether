import base64
import hashlib
import hmac
import json
import urllib.error
import urllib.request

from app.core.config import settings


class PaymentGatewayError(RuntimeError):
    pass


def gateway_is_configured() -> bool:
    return bool(
        settings.razorpay_key_id
        and settings.razorpay_key_secret
        and settings.razorpay_webhook_secret
    )


def create_order(*, amount_paise: int, currency: str, receipt: str, subscription_id: int) -> str:
    if not gateway_is_configured():
        raise PaymentGatewayError("Razorpay subscription payments are not configured")
    body = json.dumps(
        {
            "amount": amount_paise,
            "currency": currency,
            "receipt": receipt,
            "notes": {"facility_subscription_id": str(subscription_id)},
        }
    ).encode()
    credential = base64.b64encode(
        f"{settings.razorpay_key_id}:{settings.razorpay_key_secret}".encode()
    ).decode()
    request = urllib.request.Request(
        "https://api.razorpay.com/v1/orders",
        data=body,
        headers={
            "Authorization": f"Basic {credential}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            order = json.loads(response.read())
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError) as error:
        raise PaymentGatewayError("Razorpay could not create the payment order") from error
    if not isinstance(order, dict):
        raise PaymentGatewayError("Razorpay returned an invalid order response")
    order_id = order.get("id")
    if (
        not isinstance(order_id, str)
        or order.get("amount") != amount_paise
        or order.get("currency") != currency
    ):
        raise PaymentGatewayError("Razorpay returned an invalid order response")
    return order_id


def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    if not settings.razorpay_webhook_secret:
        return False
    expected = hmac.new(
        settings.razorpay_webhook_secret.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
