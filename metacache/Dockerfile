# syntax=docker/dockerfile:1
FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src
COPY . .
RUN dotnet publish src/Metacache.Host/Metacache.Host.csproj -c Release -o /app/publish

FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS final
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=build /app/publish .
# Run non-root (container-escape hardening — Trivy AVD-DS-0002 wants a USER). The
# aspnet base image defines APP_UID (1654). /app/data must pre-exist owned by that
# uid: the app creates its SQLite DB + artwork there at startup (DataPath / Images
# dir in appsettings.json) and cannot create it under the root-owned /app as
# non-root. A fresh named volume inherits this ownership on first mount; an existing
# root-owned volume needs a one-time `chown` (see README §CI/CD).
RUN mkdir -p /app/data && chown -R $APP_UID:$APP_UID /app
# Expose the provider API on the LAN (Plex registers this host:port as its provider URL).
ENV Metacache__BindAddress=0.0.0.0
EXPOSE 8765
USER $APP_UID
ENTRYPOINT ["dotnet", "Metacache.Host.dll"]
