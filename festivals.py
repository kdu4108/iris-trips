"""The 2027 festival shortlist from the Iris trips working group.

Seeded into an empty database on first boot (db.init_db). Edit here *before*
the first run; afterwards the database is the source of truth (delete iris.db
to reseed — this wipes all ballots).
"""

CODA_URL = ("https://docs.superhuman.com/d/Iris-Brain_dLU6W6zxHXd/"
            "Trips-and-exchanges_suBCzmm_#_luSwQApW")

# Iris's estimated contribution per person (CHF); shown as context only.
IRIS_CONTRIBUTION_CHF = 150

FESTIVALS = [
    {
        "name": "Chorfestival Baden",
        "place": "Baden, Germany", "flag": "🇩🇪",
        "dates": "26–31 May 2027", "cost_chf": 150,
        "blurb": "International festival, very selective.",
        "hard_to_get_in": True,
    },
    {
        "name": "International Cappadocia Choir Festival",
        "place": "Cappadocia, Turkey", "flag": "🇹🇷",
        "dates": "5–9 July 2027", "cost_chf": 500,
        "blurb": "International festival (size not specified), focused on workshops "
                 "and concerts.",
        "hard_to_get_in": False,
    },
    {
        "name": "International Choral Festival of Preveza",
        "place": "Preveza, Greece", "flag": "🇬🇷",
        "dates": "8–11 July 2027", "cost_chf": 500,
        "blurb": "Big international festival (about 400 choirs), with the "
                 "possibility of competing.",
        "hard_to_get_in": False,
    },
    {
        "name": "CantaRode International Choral Festival",
        "place": "Kerkrade, Netherlands", "flag": "🇳🇱",
        "dates": "6–10 May 2027", "cost_chf": 450,
        "blurb": "Festival for small choirs (12–40 voices, 10–14 choirs).",
        "hard_to_get_in": True,
    },
    {
        "name": "Ascona Choral Academy",
        "place": "Ascona, Switzerland", "flag": "🇨🇭",
        "dates": "3–9 October 2027", "cost_chf": 300,
        "blurb": "Workshops with the Tenebrae Choir's conductor and singers.",
        "hard_to_get_in": True,
    },
]
