import argparse
import sys

from app.db.session import SessionLocal
from app.core.audit import record_audit_event
from app.models import Facility, User


def main() -> int:
    parser = argparse.ArgumentParser(description="GetTogether operator account management")
    commands = parser.add_subparsers(dest="command", required=True)
    promote_admin = commands.add_parser("promote-admin", help="Promote an existing verified user to platform admin")
    promote_admin.add_argument("email")
    assign_staff = commands.add_parser("assign-staff", help="Assign an existing verified user to a facility")
    assign_staff.add_argument("email")
    assign_staff.add_argument("facility_id", type=int)
    args = parser.parse_args()

    with SessionLocal() as db:
        user = db.query(User).filter(User.email == args.email.strip().lower()).first()
        if user is None or not user.email_verified or not user.is_active:
            print("The account must exist, be email-verified, and be active.", file=sys.stderr)
            return 1
        if args.command == "promote-admin":
            user.role = "platform_admin"
            user.facility_id = None
        else:
            facility = db.get(Facility, args.facility_id)
            if facility is None or not facility.is_active:
                print("The requested active facility does not exist.", file=sys.stderr)
                return 1
            user.role = "facility_staff"
            user.facility_id = facility.id
        record_audit_event(db, None, f"account.{args.command}", "user", user.id)
        db.commit()
    print("Account permissions updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
