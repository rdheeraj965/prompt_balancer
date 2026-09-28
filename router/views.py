from rest_framework.views import APIView
from rest_framework.response import Response
from django.http import StreamingHttpResponse
from router.engine import RoutingEngine
from gateway.services import ModelExecutor
from django.shortcuts import render
from django.views import View

class RoutePromptView(APIView):
    def post(self, request):
        prompt = request.data.get("prompt")
        
        if not prompt:
            return Response({"error": "Prompt is required"}, status=400)
            
        # 1. Evaluate complexity, tokens, and hardware health
        selected_tier, metrics = RoutingEngine.determine_tier(prompt)
        
        # 2. Attach generator to the SSE streaming response
        stream_generator = ModelExecutor.execute_with_fallback(selected_tier, prompt)
        
        return StreamingHttpResponse(
            stream_generator, 
            content_type="text/event-stream"
        )

class DashboardView(View):
    def get(self, request):
        return render(request, 'dashboard.html')