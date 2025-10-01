from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

User = get_user_model()


class JWTAuthenticationMiddleware:
    """
    Middleware to handle JWT authentication for web requests.
    This middleware checks for JWT tokens in cookies and sets the user accordingly.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Check for JWT token in cookies
        token = request.COOKIES.get('access_token')
        if token and not request.user.is_authenticated:
            try:
                access_token = AccessToken(token)
                user_id = access_token['user_id']
                request.user = User.objects.get(id=user_id)
            except (InvalidToken, TokenError, User.DoesNotExist):
                # Token is invalid, leave user as anonymous
                pass

        response = self.get_response(request)
        return response
