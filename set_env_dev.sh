# Register the app here: https://github.com/settings/applications/new

export QUETZ_GITHUB_CLIENT_ID="37cdbb80c7733e2a1831"
export QUETZ_GITHUB_CLIENT_SECRET="75e648e981545902ab7802de94e2f2707c8e0ff8"
export QUETZ_URL="http://localhost:8000"

#openssl rand -hex 32
export QUETZ_SESSION_SECRET="b72376b88e6f249cb0921052ea8a092381ca17fd8bb0caf4d847e337b3d34cf8"
export QUETZ_SESSION_HTTPS_ONLY="false"

# QUETZ_SQLALCHEMY_DATABASE_URL = "postgresql://user:password@postgresserver/db"
export QUETZ_SQLALCHEMY_DATABASE_URL="sqlite:///./quetz.sqlite"
