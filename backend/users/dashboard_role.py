"""The Django group that limits a browser session to Certification Dashboard."""

DASHBOARD_USER_GROUP = "Dashboard User"


def is_dashboard_user(user):
    """Check current membership, including for users with other privileges."""

    return user.is_authenticated and user.groups.filter(name=DASHBOARD_USER_GROUP).exists()
