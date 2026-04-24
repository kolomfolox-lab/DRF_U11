from celery import shared_task
import time

@shared_task
def send_welcome_email(user_id):
    time.sleep(5)
    print(f"Email sent to user {user_id}")
    return True
