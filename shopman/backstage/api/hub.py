"""Central de Apps — endpoint do launcher do operador.

`GET /api/v1/backstage/hub/` → a grade de tiles permission-aware que o app
`surfaces/hub-nuxt/` consome. Qualquer operador (staff autenticado) acessa; os tiles
são filtrados por permissão dentro da projection — sem apps, grade vazia (não 403).
"""

from __future__ import annotations

from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.backstage.api.permissions import IsBackstageOperator
from shopman.backstage.api.projections import projection_data
from shopman.backstage.projections.hub import build_operator_hub


class HubView(APIView):
    permission_classes = [IsBackstageOperator]

    def get(self, request):
        hub = build_operator_hub(request.user)
        return Response({"hub": projection_data(hub)})
