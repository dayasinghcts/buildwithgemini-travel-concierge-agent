"""Seed Firestore database with initial destination data for Travel Concierge Agent."""

from google.cloud import firestore

PROJECT_ID = "qwiklabs-gcp-01-3f7f306be789"

DESTINATIONS = [
    {
        "id": "tokyo-japan",
        "name": "Tokyo",
        "country": "Japan",
        "description": "A bustling metropolis blending ultramodern skyscrapers with historic temples, world-class cuisine, and vibrant street culture.",
        "category": "Urban Exploration",
        "budget_tier": "$$$",
        "popular_activities": [
            "Shinjuku food crawl",
            "Visit Senso-ji Temple",
            "Explore Akihabara tech district",
            "Tsukiji Outer Market food tour",
        ],
        "recommended_season": "Spring (Cherry Blossom) / Autumn",
    },
    {
        "id": "kyoto-japan",
        "name": "Kyoto",
        "country": "Japan",
        "description": "The cultural capital of Japan, famous for classical Buddhist temples, gardens, imperial palaces, Shinto shrines, and traditional wooden houses.",
        "category": "Culture & History",
        "budget_tier": "$$",
        "popular_activities": [
            "Fushimi Inari Shrine torii gates",
            "Arashiyama Bamboo Grove walk",
            "Traditional tea ceremony in Gion",
            "Kinkaku-ji (Golden Pavilion)",
        ],
        "recommended_season": "Spring / Autumn",
    },
    {
        "id": "reykjavik-iceland",
        "name": "Reykjavik & Golden Circle",
        "country": "Iceland",
        "description": "Gateway to dramatic landscapes, hot springs, volcanic beaches, waterfalls, and northern lights displays.",
        "category": "Nature & Adventure",
        "budget_tier": "$$$$",
        "popular_activities": [
            "Soak in the Blue Lagoon",
            "Golden Circle waterfall tour",
            "Northern Lights night hunt",
            "Black sand beach exploration at Vik",
        ],
        "recommended_season": "Winter (Northern Lights) / Summer (Midnight Sun)",
    },
    {
        "id": "barcelona-spain",
        "name": "Barcelona",
        "country": "Spain",
        "description": "A seaside Mediterranean city renowned for modernista architecture by Gaudí, delicious tapas, sun-drenched beaches, and lively nightlife.",
        "category": "Beach & Culture",
        "budget_tier": "$$",
        "popular_activities": [
            "Tour Sagrada Família",
            "Stroll through Park Güell",
            "Tapas crawl in Gothic Quarter",
            "Relax at Barceloneta Beach",
        ],
        "recommended_season": "Spring / Late Summer",
    },
    {
        "id": "cusco-peru",
        "name": "Cusco & Machu Picchu",
        "country": "Peru",
        "description": "Ancient capital of the Inca Empire in the Andes, serving as the launching point for exploring the Sacred Valley and Machu Picchu.",
        "category": "Adventure & History",
        "budget_tier": "$$",
        "popular_activities": [
            "Hike the Inca Trail to Machu Picchu",
            "Explore Sacred Valley salt mines",
            "San Pedro market food tasting",
            "Visit Sacsayhuamán fortress",
        ],
        "recommended_season": "Dry season (May to October)",
    },
]


def seed_database():
    """Populate Firestore destinations collection."""
    db = firestore.Client(project=PROJECT_ID)
    destinations_ref = db.collection("destinations")

    print(f"Seeding Firestore in project '{PROJECT_ID}'...")
    for item in DESTINATIONS:
        doc_id = item["id"]
        data = {k: v for k, v in item.items() if k != "id"}
        destinations_ref.document(doc_id).set(data)
        print(f"  ✓ Added destination: {item['name']} ({doc_id})")

    print("Seeding complete! 🚀")


if __name__ == "__main__":
    seed_database()
