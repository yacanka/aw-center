from django.utils.deprecation import MiddlewareMixin
from django.utils import timezone

class RequestUserLogMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if request.user and request.user.is_authenticated:
            username = request.user.username
        else:
            username = "Anonymous"
        
        ip = self.get_client_ip(request)
        
        method = request.method
        
        path = request.path
        
        now = timezone.localtime().strftime("%d.%m.%Y %H:%M:%S")
        
        print(f"[{now}] {ip} - {username}: {method} {path}")
        
        return None
    
    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip