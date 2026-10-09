"""Słowniki polskich nazw, miast, ulic i branż."""

FIRST_M = ["Jan", "Piotr", "Krzysztof", "Andrzej", "Tomasz", "Paweł", "Michał", "Marcin",
           "Grzegorz", "Jakub", "Adam", "Łukasz", "Mateusz", "Marek", "Kamil", "Wojciech",
           "Rafał", "Dariusz", "Bartosz", "Szymon", "Maciej", "Damian", "Sebastian", "Filip",
           "Karol", "Robert", "Przemysław", "Artur", "Dawid", "Hubert"]
FIRST_F = ["Anna", "Maria", "Katarzyna", "Małgorzata", "Agnieszka", "Barbara", "Ewa",
           "Magdalena", "Joanna", "Aleksandra", "Monika", "Natalia", "Karolina", "Marta",
           "Zofia", "Julia", "Dorota", "Beata", "Paulina", "Justyna", "Weronika", "Iwona",
           "Agata", "Kinga", "Emilia", "Patrycja", "Sylwia", "Alicja", "Hanna", "Izabela"]
LAST_M = ["Nowak", "Kowalski", "Wiśniewski", "Wójcik", "Kowalczyk", "Kamiński", "Lewandowski",
          "Zieliński", "Szymański", "Woźniak", "Dąbrowski", "Kozłowski", "Jankowski",
          "Mazur", "Kwiatkowski", "Krawczyk", "Piotrowski", "Grabowski", "Nowakowski",
          "Pawłowski", "Michalski", "Nowicki", "Adamczyk", "Dudek", "Zając", "Wieczorek",
          "Jabłoński", "Król", "Majewski", "Olszewski", "Jaworski", "Wróbel", "Malinowski",
          "Pawlak", "Witkowski", "Walczak", "Stępień", "Górski", "Rutkowski", "Michalak",
          "Sikora", "Ostrowski", "Baran", "Duda", "Szewczyk", "Tomaszewski", "Pietrzak",
          "Marciniak", "Wróblewski", "Zalewski", "Jakubowski", "Jasiński", "Zawadzki",
          "Sadowski", "Bąk", "Chmielewski", "Włodarczyk", "Borkowski", "Czarnecki", "Sawicki"]


def female_last(name: str) -> str:
    if name.endswith("ski"):
        return name[:-3] + "ska"
    if name.endswith("cki"):
        return name[:-3] + "cka"
    if name.endswith("dzki"):
        return name[:-4] + "dzka"
    return name


# miasto: (waga biur B2B, prefiksy kodów pocztowych)
CITIES = {
    "Poznań": (0.24, ["60", "61"]),
    "Warszawa": (0.22, ["00", "01", "02", "03", "04"]),
    "Wrocław": (0.09, ["50", "51", "52", "53", "54"]),
    "Kraków": (0.08, ["30", "31"]),
    "Gdańsk": (0.05, ["80"]),
    "Łódź": (0.04, ["90", "91", "92", "93", "94"]),
    "Katowice": (0.04, ["40"]),
    "Szczecin": (0.03, ["70", "71"]),
    "Bydgoszcz": (0.025, ["85"]),
    "Gdynia": (0.02, ["81"]),
    "Lublin": (0.018, ["20"]),
    "Białystok": (0.012, ["15"]),
    "Rzeszów": (0.012, ["35"]),
    "Toruń": (0.012, ["87"]),
    "Kalisz": (0.01, ["62"]),
    "Leszno": (0.008, ["64"]),
    "Piła": (0.007, ["64"]),
    "Gniezno": (0.007, ["62"]),
    "Opole": (0.008, ["45"]),
    "Kielce": (0.007, ["25"]),
    "Olsztyn": (0.007, ["10"]),
    "Zielona Góra": (0.007, ["65"]),
    "Gorzów Wielkopolski": (0.006, ["66"]),
    "Swarzędz": (0.008, ["62"]),
    "Luboń": (0.004, ["62"]),
    "Konin": (0.004, ["62"]),
    "Sopot": (0.004, ["81"]),
    "Gliwice": (0.006, ["44"]),
    "Częstochowa": (0.004, ["42"]),
    "Radom": (0.003, ["26"]),
}

STREETS = ["Głogowska", "Grunwaldzka", "Bukowska", "Garbary", "Dąbrowskiego", "Półwiejska",
           "Królowej Jadwigi", "Marcinkowskiego", "Św. Marcin", "Roosevelta", "Hetmańska",
           "Marszałkowska", "Puławska", "Prosta", "Grzybowska", "Domaniewska", "Wołoska",
           "Jana Pawła II", "Mickiewicza", "Słowackiego", "Kościuszki", "Piłsudskiego",
           "Sienkiewicza", "Długa", "Polna", "Leśna", "Ogrodowa", "Kolejowa", "Szkolna",
           "Lipowa", "Wrocławska", "Krakowska", "Gdańska", "Kasprzaka", "Towarowa", "Fabryczna",
           "Przemysłowa", "Składowa", "Wierzbięcice", "Strzeszyńska", "Szwedzka", "Baraniaka",
           "Abpa. Baraniaka", "Murawa", "Obornicka", "Serbska", "Al. Solidarności",
           "Al. Niepodległości", "Al. Jerozolimskie", "Legnicka", "Powstańców Śląskich"]

BRANZE = ["IT – software house", "IT – usługi chmurowe", "Kancelaria prawna", "Biuro rachunkowe",
          "Doradztwo podatkowe", "Agencja reklamowa", "Agencja marketingu cyfrowego",
          "Biuro architektoniczne", "Biuro projektowe – inżynieria", "Bank", "Ubezpieczenia",
          "Leasing", "Fintech", "Nieruchomości – deweloper", "Nieruchomości – zarządca",
          "Logistyka i spedycja", "E-commerce", "Produkcja – maszyny", "Produkcja – FMCG",
          "Farmacja", "Medycyna – przychodnia", "Stomatologia", "Edukacja – szkoła językowa",
          "Edukacja – uczelnia", "Badania i rozwój", "Media i wydawnictwa", "Telekomunikacja",
          "Energetyka", "Motoryzacja – salon", "Rekrutacja i HR", "Outsourcing BPO/SSC",
          "Consulting zarządczy", "Administracja publiczna", "Organizacja pozarządowa",
          "Hotelarstwo", "Turystyka", "Budownictwo", "Handel hurtowy", "Gaming", "Coworking"]

COMPANY_PREFIX = ["Biurowiec", "Grupa", "Studio", "Centrum", "Kancelaria", "Agencja", "Instytut",
                  "Pracownia", "Dom", "Zakłady", "Przedsiębiorstwo", "Spółdzielnia", "Fundacja",
                  "Biuro", "Laboratorium", "Hub", "Park", "Centrala"]
COMPANY_CORE = ["Delta", "Orion", "Atlas", "Vega", "Nova", "Magnum", "Polaris", "Sigma", "Omega",
                "Alfa", "Kappa", "Lambda", "Argo", "Horyzont", "Warta", "Cytadela", "Stary Rynek",
                "Wilda", "Jeżyce", "Malta", "Piątkowo", "Rataje", "Łazarz", "Sołacz", "Winogrady",
                "Bałtyk", "Tatry", "Sudety", "Mazowsze", "Wielkopolska", "Odra", "Wisła", "Noteć",
                "Promień", "Zenit", "Kometa", "Meteor", "Kwadrant", "Pryzmat", "Fokus", "Impuls",
                "Kompas", "Mosty", "Filar", "Arkada", "Patio", "Aleja", "Bastion", "Kopernik",
                "Heweliusz", "Skłodowska", "Chopin", "Paderewski", "Brda", "Prosna", "Gopło",
                "Lednica", "Morasko", "Strzeszyn", "Naramowice", "Junikowo", "Ławica", "Kiekrz",
                "Rusałka", "Cybina", "Szeląg", "Garbary", "Chwaliszewo", "Ostrów", "Śródka",
                "Dębiec", "Starołęka", "Antoninek", "Smochowice", "Krzesiny", "Pokrzywno",
                "Spichlerz", "Młyn", "Browar", "Kamienica", "Dworzec", "Port", "Latarnia",
                "Czwórka", "Pion", "Poziom", "Kwartet", "Synergia", "Iskra", "Wektor", "Tangens",
                "Logos", "Ethos", "Medius", "Primus", "Optima", "Maxima", "Integra", "Concordia"]
LEGAL = ["Sp. z o.o.", "S.A.", "Sp. z o.o. Sp. k.", "Sp. j.", "Sp. k.", "s.c."]
LEGAL_W = [0.62, 0.1, 0.1, 0.06, 0.07, 0.05]

AM_NAMES = ["Katarzyna Wiśniewska", "Tomasz Kaczmarek", "Agnieszka Lewandowska",
            "Michał Zieliński", "Joanna Wójcik", "Paweł Dąbrowski"]
AM_REGION = ["Poznań i Wielkopolska", "Warszawa i Mazowsze", "Poznań i Wielkopolska",
             "Południe (Kraków, Katowice, Wrocław)", "Północ (Gdańsk, Gdynia, Szczecin)",
             "Centrum i pozostałe"]

EMAIL_DOMAINS_PL = ["gmail.com", "wp.pl", "onet.pl", "o2.pl", "interia.pl", "op.pl",
                    "outlook.com", "icloud.com", "poczta.fm", "tlen.pl"]
EMAIL_DOMAINS_DE = ["gmx.de", "web.de", "t-online.de", "gmail.com", "posteo.de"]
DE_FIRST = ["Lukas", "Anna", "Jonas", "Lea", "Felix", "Laura", "Max", "Sophie", "Paul", "Marie",
            "Leon", "Hannah", "Tim", "Lena", "Niklas", "Julia"]
DE_LAST = ["Müller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer", "Wagner", "Becker",
           "Schulz", "Hoffmann", "Koch", "Richter", "Klein", "Wolf", "Neumann", "Kowalski"]

TRANSLIT = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻäöüß", "acelnoszzACELNOSZZaous")
