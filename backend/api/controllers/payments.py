from datetime import datetime, date
import os
import stripe
from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select
from api.db.database import engine
from api.db.models import User, Plan, Status, Subscription
from api.db.database import get_session
from api.controllers.auth import get_current_user
from dotenv import load_dotenv
from pathlib import Path
from fastapi.responses import FileResponse, RedirectResponse

env_path = Path(__file__).parent.parent.parent / ".env"

if env_path.exists():
    load_dotenv(dotenv_path=env_path, override=True)
    print(f"payments.py Success: Loaded .env")
else:
    print(f"payments.py Error: Could not find .env at {env_path.absolute()}")


router = APIRouter()
load_dotenv()

# Sandbox keys (for testing)
stripe_public_key = os.getenv("TEST_STRIPE_PUBLIC_KEY")
stripe_secret_key = os.getenv("TEST_STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("TEST_WEBHOOK_SECRET")
pro_plan = os.getenv("TEST_PRO_PLAN")

# Live keys (for production in live environment)
# stripe_public_key = os.getenv("STRIPE_PUBLIC_KEY")
# stripe_secret_key = os.getenv("STRIPE_SECRET_KEY")
# STRIPE_WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
# pro_plan = os.getenv("PRO_PLAN")

# use this if want to work with server and healthfactchecker.site
# DOMAIN = os.getenv("DOMAIN_PUBLIC") 

# use this line if want to test with localhost
# but then must change STRIPE_WEBHOOK_SECRET to the one generated for localhost by yourself
# use this link to generate webhook secret for localhost testing: https://docs.stripe.com/stripe-cli/install
DOMAIN = os.getenv("DOMAIN_LOCAL") 

stripe.api_key = stripe_secret_key

def map_stripe_status_to_id(stripe_status: str) -> int:
    # Mapping Stripe's internal strings to MariaDB IDs
    mapping = {
        "active": 1,           # Aktyvi
        "trialing": 1,         # Aktyvi 
        "canceled": 2,         # Atsaukta
        "incomplete_expired": 2, # Atsaukta
        "past_due": 3,         # Sustabdyta 
        "unpaid": 3,           # Sustabdyta
        "paused": 3            # Sustabdyta
    }
    # Default to 'Sustabdyta' (3) if status is unknown for safety
    return mapping.get(stripe_status, 3)

# generating checkout session when user clicks 'Upgrade' in Plugin
@router.post("/create-checkout-session")
async def create_checkout(email: str, db: Session = Depends(get_session)):
    statement = select(User).where(User.email == email)
    user = db.exec(statement).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Ensure the user exists in Stripe
    if not user.stripe_customer_id:
        customer = stripe.Customer.create(email=email)
        user.stripe_customer_id = customer.id
        db.add(user)
        db.commit()

    try:
        checkout_session = stripe.checkout.Session.create(
            customer=user.stripe_customer_id,
            client_reference_id=str(user.id),  # CRITICAL: Links the session to  DB User ID
            line_items=[{
                'price': pro_plan, # This is the Price ID from Stripe Dashboard
                'quantity': 1,
            }],
            mode='subscription',
            success_url=f"{DOMAIN}/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{DOMAIN}/cancel",
        )
        return {"url": checkout_session.url}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# webhook (The background listener that updates MariaDB)
@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_session)):
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid signature")

    session = event['data']['object'] 
    # INITIAL PURCHASE
    if event['type'] == 'checkout.session.completed':
        user_id = session.client_reference_id
        stripe_sub_id = session.subscription

        if not user_id:
            print("Warning: No user_id found in session")
            return {"status": "ignored"}
        
        elif user_id:
            new_sub = Subscription(
                user_id=int(user_id),
                stripe_subscription_id=stripe_sub_id, # Maps to Stripe_Prenumeratos_ID
                plan_name="pro",                      # Maps to Plano_Pavadinimas
                status_id=1,
                queries_performed=0,
                start_time=date.today(),
                renewal_time=date.fromtimestamp(datetime.now().timestamp() + 2592000)
            )
            db.add(new_sub)

            # Also update the User table to store the Stripe Customer ID 
            user_stmt = select(User).where(User.id == int(user_id))
            user = db.exec(user_stmt).first()
            if user:
                user.stripe_customer_id = session.customer #data_object.get('customer') # Maps to Stripe_Kliento_ID
            db.add(user)
            db.commit()
            print(f"Success! Updating user {user_id}")

    # RENEWALS, CANCELLATIONS, OR FAILURES
    elif event['type'] in ['customer.subscription.updated', 'customer.subscription.deleted']:
        stripe_sub_id = session.id
        new_status = session.status
        
        sub_stmt = select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
        db_sub = db.exec(sub_stmt).first()
        
        if db_sub:
            db_sub.status_id = map_stripe_status_to_id(new_status)
            db_sub.renewal_time = date.fromtimestamp(session.current_period_end)
            db.add(db_sub)
            db.commit()

    return {"status": "success"}


@router.get("/user-status")
def get_user_status(
    current_user: User = Depends(get_current_user), # Use your JWT dependency
    session: Session = Depends(get_session)
):
    # calling helper
    return get_subscription_info(current_user.id, current_user.email, session)    

def get_subscription_info(user_id: int, user_email: str, session: Session):
    # Find the newest subscription record
    statement = (
        select(Subscription)
        .where(Subscription.user_id == user_id)
        .order_by(Subscription.id.desc())
    )
    latest_sub = session.exec(statement).first()

    if latest_sub and latest_sub.status_id == 1:
        return {
            "isActive": True,
            "plan": latest_sub.plan_name,
            "queries_performed": latest_sub.queries_performed,
            "renewal_time": latest_sub.renewal_time
        }
    
    return {
        "isActive": False,
        "plan": "free",
        "queries_performed": 0,
        "renewal_time": None
    }

# generating billing portal session
@router.post("/create-portal-session")
async def create_portal(
    # Using Form(...) so FastAPI looks in the POST body
    session_id: str = Form(...) 
):
    try:
        # Retrieving the original checkout session from Stripe (safer than passing email)
        checkout_session = stripe.checkout.Session.retrieve(session_id)
        customer_id = checkout_session.customer

        if not customer_id:
            raise HTTPException(status_code=400, detail="No customer associated with this session")

        # creating the Billing Portal session
        portal_session = stripe.billing_portal.Session.create(
            customer=customer_id,
            # Where the user goes when they click "Back" in the portal
            return_url=f"{DOMAIN}/success?session_id={session_id}",
        )

        # using RedirectResponse so the browser actually GOES to the page
        return RedirectResponse(portal_session.url, status_code=303)

    except Exception as e:
        print(f"Portal Error: {e}")
        raise HTTPException(status_code=500, detail="Could not create billing portal")

HTML_DIR = Path(__file__).parent.parent.parent.parent / "frontend" 

@router.get("/success")
async def payment_success():
    file_path = HTML_DIR / "success.html"
    
    if not file_path.exists():
        # Fallback if the path is wrong
        return {"error": f"File not found at {file_path}"}
        
    return FileResponse(file_path)

@router.get("/cancel")
async def cancel_page():
    file_path = HTML_DIR / "cancel.html"

    if not file_path.exists():
        return {"error": f"File not found at {file_path}"}
    return FileResponse(file_path)

@router.get("/exit")
async def exit_page():
    file_path = HTML_DIR / "exit.html"

    if not file_path.exists():
        return {"error": f"File not found at {file_path}"}
    return FileResponse(file_path)


@router.post("/create-portal-session")
async def create_portal_session(
    session_id: str = Form(...) # Get session_id from form data
):
    try:
        # Retrieve the checkout session using the ID from the form
        checkout_session = stripe.checkout.Session.retrieve(session_id)
        
        # Get the customer ID from that session
        customer_id = checkout_session.customer

        # Create the portal
        portal_session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=f"{DOMAIN}/success?session_id=" + session_id,
        )
        return RedirectResponse(portal_session.url, status_code=303)
    except Exception as e:
        print(f"Portal Error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    

@router.get("/create-portal-session2")
async def create_portal_session(
    current_user: User = Depends(get_current_user) # Identified by token
):
    #  Check if the user even has a Stripe ID
    if not current_user.stripe_customer_id:
        raise HTTPException(status_code=404, detail="Stripe customer not found")

    try:
        # Create the portal session
        session = stripe.billing_portal.Session.create(
            customer=current_user.stripe_customer_id,
            return_url=f"{DOMAIN}/exit" 
        )
        return {"url": session.url}
        
    except Exception as e:
        print(f"Portal Error: {e}")
        raise HTTPException(status_code=500, detail="Could not create portal")
    

    
