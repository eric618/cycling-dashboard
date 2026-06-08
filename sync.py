"""
sync.py — Ejecutar localmente después de cada entrenamiento.
Conecta a Garmin Connect (funciona desde tu Mac) y sube los datos a Supabase.

Uso:
    python3 sync.py                       # sincroniza resúmenes de las últimas 30 actividades
    python3 sync.py --all                 # sincroniza hasta 500 actividades
    python3 sync.py --streams             # además descarga streams de potencia/FC/cadencia/GPS (más lento)
    python3 sync.py --streams --ftp 260   # usa un FTP específico para el cálculo de TSS
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
    parser.add_argument("--streams",  action="store_true", help="También descarga streams (potencia/FC/cadencia/GPS) — más lento")
    parser.add_argument("--ftp",      type=int, default=None, help="FTP en watts para cálculo de TSS (default: del .env)")
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
    print("☁️  Subiendo resúmenes a Supabase...")
    from data.cache import upsert_activity, get_activity
    from config import DEFAULT_FTP
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

    print(f"✅ Resúmenes: {len(activities) - errors} subidas, {errors} errores.")

    # --- Streams (opcional, más lento: 1 request extra por actividad) ---
    if args.streams:
        ftp = args.ftp or DEFAULT_FTP
        print(f"\n📊 Descargando streams (potencia/FC/cadencia/GPS) — FTP={ftp}W...")
        from data.stream_processor import fetch_and_store_activity_detail

        pending = [a for a in activities
                   if not (get_activity(str(a.get("activityId") or a.get("id"))) or {}).get("detail_fetched")]
        print(f"   {len(pending)} actividades sin streams aún.")

        fetched, skipped, stream_errors = 0, 0, 0
        for i, act in enumerate(pending, 1):
            act_id = str(act.get("activityId") or act.get("id"))
            cached = get_activity(act_id) or {}
            try:
                found = fetch_and_store_activity_detail(client, act_id, cached, ftp)
                if found:
                    fetched += 1
                else:
                    skipped += 1
            except Exception as e:
                print(f"   ⚠️  Streams actividad {act_id}: {e}")
                stream_errors += 1
            if i % 10 == 0:
                print(f"   {i}/{len(pending)}...")

        print(f"✅ Streams: {fetched} con datos de potencia, {skipped} sin potenciómetro, {stream_errors} errores.")

    print("\n🎉 Sincronización completa. Abre tu dashboard para ver los datos actualizados.")
    if not args.streams:
        print("   Tip: usa --streams para también descargar series de potencia/FC/cadencia (más lento).")


if __name__ == "__main__":
    main()
