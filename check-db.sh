#!/bin/bash

# Sprawdź bazę danych MeshScout

cd "$(dirname "$0")"

echo "🔍 Uruchamiam sprawdzanie bazy danych..."
echo ""

# Sprawdź czy istnieje plik .env
if [ ! -f .env ]; then
    echo "❌ Brak pliku .env! Kopiuję z .env.example..."
    cp .env.example .env
    echo "⚠️  UWAGA: Musisz skonfigurować DATABASE_URL w .env!"
    exit 1
fi

# Pobierz DATABASE_URL z .env
source .env

# Sprawdź czy DATABASE_URL jest ustawiony
if [ -z "$DATABASE_URL" ]; then
    echo "❌ DATABASE_URL nie jest ustawiony w .env!"
    exit 1
fi

echo "📊 Łączę z bazą danych..."
echo ""

# Wykonaj zapytania SQL
psql "$DATABASE_URL" -f scripts/check-db.sql
