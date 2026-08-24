from rest_framework import serializers


class InstallRequestSerializer(serializers.Serializer):
    """Matches the FastAPI-era catalog router's InstallRequest(BaseModel):
    confirm defaults to False, so an omitted field is treated as an
    explicit no."""

    confirm = serializers.BooleanField(default=False)


class RemoveRequestSerializer(serializers.Serializer):
    """Matches the FastAPI-era catalog router's RemoveRequest(BaseModel):
    confirm and remove_volumes both default to False."""

    confirm = serializers.BooleanField(default=False)
    remove_volumes = serializers.BooleanField(default=False)
