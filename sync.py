"""
sync.py — Ejecutar localmente después de cada entrenamiento.
Conecta a Garmin Connect (funciona desde tu Mac) y sube los datos a Supabase.

Uso:
    python3 sync.py              # sincroniza las últimas 30 actividades
    python3 sync.py --all        # sincroniza hasta 500 actividades
    python3 sync.py --email tu@email.com --password tupassword
"""
import argparse
import sys
from dotenv import load_dotenv

load_dotenv()


def main():
    parser = argparse.ArgumentParser(description="Sync Garmin → Supabase")
    parser.add_argument("--email",    default=None)
    parser.add_argument("--password", default=None)
    parser.add_argument("--all",      action="store_true", help="Sincroniza todas las actividades")
    parser.add_argument("--limit",    type=int, default=30, help="Número de actividades (default: 30)")
    args = parser.parse_args()

    # Credentials
    from config import GARMIN_EMAIL, GARMIN_PASSWORD
    email    = args.email    or GARMIN_EMAIL
    password = args.password or GARMIN_PASSWORD

    if not email or not password:
        print("❌ Falta email o contraseña.")
        print("   Ponlos en el .env o usa: python3 sync.py --email X --password Y")
        sys.exit(1)

    # Login Garmin
    print(f"🔐 Conectando a Garmin Connect como {email}...")
    from garminconnect import Garmin, GarminConnectAuthenticationError
    try:
        client = Garmin(email, password)
        client.login()
        print("✅ Conectado.")
    except GarminConnectAuthenticationError:
        print("❌ Credenciales incorrectas.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error al conectar: {e}")
        sys.exit(1)

    # Fetch activities
    limit = 500 if args.all else args.limit
    print(f"📥 Descargando {limit} actividades...")
    from api.garmin_client import get_all_activities
    activities = get_all_activities(client, max_activities=limit)
    print(f"   {len(activities)} actividades obtenidas.")

    # Upsert to Supabase
    print("☁️  Subiendo a Supabase...")
    from data.cache import upsert_activity
    athlete_id = email
    errors = 0
    for i, act in enumerate(activities, 1):
        try:
            upsert_activity(act, athlete_id=athlete_id)
        except Exception as e:
            print(f"   ⚠️  Actividad {act.get('activityId', '?')}: {e}")
            errors += 1
        if i % 50 == 0:
            print(f"   {i}/{len(activities)}...")

    print(f"\n✅ Sincronización completa: {len(activities) - errors} actividades subidas, {errors} errores.")
    print("   Abre tu dashboard para ver los datos actualizados.")


if __name__ == "__main__":
    main()
