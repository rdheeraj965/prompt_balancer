import uuid
from django.shortcuts import render
from django.views import View
from django.http import StreamingHttpResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from router.engine import RoutingEngine
from router.monitor import SystemMonitor
from gateway.services import ModelExecutor
from gateway.memory import ConversationMemory
from gateway.analytics import AnalyticsTracker

class DashboardView(View):
    def get(self, request):
        return render(request, "dashboard.html")

class RoutePromptView(APIView):
    def post(self, request):
        prompt = request.data.get("prompt")
        session_id = request.data.get("session_id") or str(uuid.uuid4())
        forced_tier = request.data.get("forced_tier") or None

        if not prompt:
            return Response({"error": "Prompt is required"}, status=400)

        stream_generator = ModelExecutor.execute_chat_stream(
            prompt=prompt,
            session_id=session_id,
            router_fn=RoutingEngine.determine_tier,
            forced_tier=forced_tier,
        )

        response = StreamingHttpResponse(stream_generator, content_type="text/event-stream")
        response["X-Session-ID"] = session_id
        return response

class ResetChatView(APIView):
    def post(self, request):
        session_id = request.data.get("session_id")
        ConversationMemory.clear(session_id)
        return Response({"status": "cleared", "session_id": session_id})

class SyncChatView(APIView):
    def post(self, request):
        session_id = request.data.get("session_id")
        messages = request.data.get("messages", [])
        ConversationMemory.sync_history(session_id, messages)
        return Response({"status": "synced", "session_id": session_id, "count": len(messages)})

class SystemHealthView(APIView):
    def get(self, request):
        return Response(SystemMonitor.check_local_health())

class AnalyticsView(APIView):
    def get(self, request):
        return Response(AnalyticsTracker.get_summary())

    def post(self, request):
        AnalyticsTracker.clear()
        return Response({"status": "cleared"})