"""Selecciones nacionales: nombre en español, bandera (flagcdn.com) y código de tres letras.

Los resultados vienen en inglés (martj42/international_results). `nombre()` los pasa a español; los países que no
están en la tabla conservan su nombre original y se muestran con una insignia de iniciales en vez de bandera.
"""
# nombre en inglés -> (nombre en español, código de bandera ISO, código de tres letras)
PAISES = {
    # --- Europa (UEFA)
    "Albania": ("Albania", "al", "ALB"), "Andorra": ("Andorra", "ad", "AND"), "Armenia": ("Armenia", "am", "ARM"),
    "Austria": ("Austria", "at", "AUT"), "Azerbaijan": ("Azerbaiyán", "az", "AZE"), "Belarus": ("Bielorrusia", "by", "BLR"),
    "Belgium": ("Bélgica", "be", "BEL"), "Bosnia and Herzegovina": ("Bosnia y Herzegovina", "ba", "BIH"),
    "Bulgaria": ("Bulgaria", "bg", "BUL"), "Croatia": ("Croacia", "hr", "CRO"), "Cyprus": ("Chipre", "cy", "CYP"),
    "Czech Republic": ("Chequia", "cz", "CZE"), "Denmark": ("Dinamarca", "dk", "DEN"), "England": ("Inglaterra", "gb-eng", "ENG"),
    "Estonia": ("Estonia", "ee", "EST"), "Faroe Islands": ("Islas Feroe", "fo", "FRO"), "Finland": ("Finlandia", "fi", "FIN"),
    "France": ("Francia", "fr", "FRA"), "Georgia": ("Georgia", "ge", "GEO"), "Germany": ("Alemania", "de", "GER"),
    "Gibraltar": ("Gibraltar", "gi", "GIB"), "Greece": ("Grecia", "gr", "GRE"), "Hungary": ("Hungría", "hu", "HUN"),
    "Iceland": ("Islandia", "is", "ISL"), "Israel": ("Israel", "il", "ISR"), "Italy": ("Italia", "it", "ITA"),
    "Kazakhstan": ("Kazajistán", "kz", "KAZ"), "Kosovo": ("Kosovo", "xk", "KOS"), "Latvia": ("Letonia", "lv", "LVA"),
    "Liechtenstein": ("Liechtenstein", "li", "LIE"), "Lithuania": ("Lituania", "lt", "LTU"), "Luxembourg": ("Luxemburgo", "lu", "LUX"),
    "Malta": ("Malta", "mt", "MLT"), "Moldova": ("Moldavia", "md", "MDA"), "Montenegro": ("Montenegro", "me", "MNE"),
    "Netherlands": ("Países Bajos", "nl", "NED"), "North Macedonia": ("Macedonia del Norte", "mk", "MKD"),
    "Northern Ireland": ("Irlanda del Norte", "gb-nir", "NIR"), "Norway": ("Noruega", "no", "NOR"), "Poland": ("Polonia", "pl", "POL"),
    "Portugal": ("Portugal", "pt", "POR"), "Republic of Ireland": ("Irlanda", "ie", "IRL"), "Romania": ("Rumanía", "ro", "ROU"),
    "Russia": ("Rusia", "ru", "RUS"), "San Marino": ("San Marino", "sm", "SMR"), "Scotland": ("Escocia", "gb-sct", "SCO"),
    "Serbia": ("Serbia", "rs", "SRB"), "Slovakia": ("Eslovaquia", "sk", "SVK"), "Slovenia": ("Eslovenia", "si", "SVN"),
    "Spain": ("España", "es", "ESP"), "Sweden": ("Suecia", "se", "SWE"), "Switzerland": ("Suiza", "ch", "SUI"),
    "Turkey": ("Turquía", "tr", "TUR"), "Ukraine": ("Ucrania", "ua", "UKR"), "Wales": ("Gales", "gb-wls", "WAL"),
    # --- Sudamérica (CONMEBOL)
    "Argentina": ("Argentina", "ar", "ARG"), "Bolivia": ("Bolivia", "bo", "BOL"), "Brazil": ("Brasil", "br", "BRA"),
    "Chile": ("Chile", "cl", "CHI"), "Colombia": ("Colombia", "co", "COL"), "Ecuador": ("Ecuador", "ec", "ECU"),
    "Paraguay": ("Paraguay", "py", "PAR"), "Peru": ("Perú", "pe", "PER"), "Uruguay": ("Uruguay", "uy", "URU"),
    "Venezuela": ("Venezuela", "ve", "VEN"),
    # --- Norte y Centroamérica, Caribe (CONCACAF)
    "Antigua and Barbuda": ("Antigua y Barbuda", "ag", "ATG"), "Aruba": ("Aruba", "aw", "ARU"), "Bahamas": ("Bahamas", "bs", "BAH"),
    "Barbados": ("Barbados", "bb", "BRB"), "Belize": ("Belice", "bz", "BLZ"), "Bermuda": ("Bermudas", "bm", "BER"),
    "Canada": ("Canadá", "ca", "CAN"), "Cayman Islands": ("Islas Caimán", "ky", "CAY"), "Costa Rica": ("Costa Rica", "cr", "CRC"),
    "Cuba": ("Cuba", "cu", "CUB"), "Curaçao": ("Curazao", "cw", "CUW"), "Dominica": ("Dominica", "dm", "DMA"),
    "Dominican Republic": ("República Dominicana", "do", "DOM"), "El Salvador": ("El Salvador", "sv", "SLV"),
    "Grenada": ("Granada", "gd", "GRN"), "Guatemala": ("Guatemala", "gt", "GUA"), "Guyana": ("Guyana", "gy", "GUY"),
    "Haiti": ("Haití", "ht", "HAI"), "Honduras": ("Honduras", "hn", "HON"), "Jamaica": ("Jamaica", "jm", "JAM"),
    "Mexico": ("México", "mx", "MEX"), "Montserrat": ("Montserrat", "ms", "MSR"), "Nicaragua": ("Nicaragua", "ni", "NCA"),
    "Panama": ("Panamá", "pa", "PAN"), "Puerto Rico": ("Puerto Rico", "pr", "PUR"),
    "Saint Kitts and Nevis": ("San Cristóbal y Nieves", "kn", "SKN"), "Saint Lucia": ("Santa Lucía", "lc", "LCA"),
    "Saint Vincent and the Grenadines": ("San Vicente y las Granadinas", "vc", "VIN"), "Suriname": ("Surinam", "sr", "SUR"),
    "Trinidad and Tobago": ("Trinidad y Tobago", "tt", "TRI"), "United States": ("Estados Unidos", "us", "USA"),
    # --- África (CAF)
    "Algeria": ("Argelia", "dz", "ALG"), "Angola": ("Angola", "ao", "ANG"), "Benin": ("Benín", "bj", "BEN"),
    "Botswana": ("Botsuana", "bw", "BOT"), "Burkina Faso": ("Burkina Faso", "bf", "BFA"), "Burundi": ("Burundi", "bi", "BDI"),
    "Cameroon": ("Camerún", "cm", "CMR"), "Cape Verde": ("Cabo Verde", "cv", "CPV"),
    "Central African Republic": ("República Centroafricana", "cf", "CTA"), "Chad": ("Chad", "td", "CHA"),
    "Comoros": ("Comoras", "km", "COM"), "Congo": ("Congo", "cg", "CGO"), "DR Congo": ("RD del Congo", "cd", "COD"),
    "Djibouti": ("Yibuti", "dj", "DJI"), "Egypt": ("Egipto", "eg", "EGY"), "Equatorial Guinea": ("Guinea Ecuatorial", "gq", "EQG"),
    "Eritrea": ("Eritrea", "er", "ERI"), "Eswatini": ("Esuatini", "sz", "SWZ"), "Ethiopia": ("Etiopía", "et", "ETH"),
    "Gabon": ("Gabón", "ga", "GAB"), "Gambia": ("Gambia", "gm", "GAM"), "Ghana": ("Ghana", "gh", "GHA"),
    "Guinea": ("Guinea", "gn", "GUI"), "Guinea-Bissau": ("Guinea-Bisáu", "gw", "GNB"), "Ivory Coast": ("Costa de Marfil", "ci", "CIV"),
    "Kenya": ("Kenia", "ke", "KEN"), "Lesotho": ("Lesoto", "ls", "LES"), "Liberia": ("Liberia", "lr", "LBR"),
    "Libya": ("Libia", "ly", "LBY"), "Madagascar": ("Madagascar", "mg", "MAD"), "Malawi": ("Malaui", "mw", "MWI"),
    "Mali": ("Malí", "ml", "MLI"), "Mauritania": ("Mauritania", "mr", "MTN"), "Mauritius": ("Mauricio", "mu", "MRI"),
    "Morocco": ("Marruecos", "ma", "MAR"), "Mozambique": ("Mozambique", "mz", "MOZ"), "Namibia": ("Namibia", "na", "NAM"),
    "Niger": ("Níger", "ne", "NIG"), "Nigeria": ("Nigeria", "ng", "NGA"), "Rwanda": ("Ruanda", "rw", "RWA"),
    "São Tomé and Príncipe": ("Santo Tomé y Príncipe", "st", "STP"), "Senegal": ("Senegal", "sn", "SEN"),
    "Seychelles": ("Seychelles", "sc", "SEY"), "Sierra Leone": ("Sierra Leona", "sl", "SLE"), "Somalia": ("Somalia", "so", "SOM"),
    "South Africa": ("Sudáfrica", "za", "RSA"), "South Sudan": ("Sudán del Sur", "ss", "SSD"), "Sudan": ("Sudán", "sd", "SDN"),
    "Tanzania": ("Tanzania", "tz", "TAN"), "Togo": ("Togo", "tg", "TOG"), "Tunisia": ("Túnez", "tn", "TUN"),
    "Uganda": ("Uganda", "ug", "UGA"), "Zambia": ("Zambia", "zm", "ZAM"), "Zimbabwe": ("Zimbabue", "zw", "ZIM"),
    # --- Asia (AFC)
    "Afghanistan": ("Afganistán", "af", "AFG"), "Australia": ("Australia", "au", "AUS"), "Bahrain": ("Baréin", "bh", "BHR"),
    "Bangladesh": ("Bangladés", "bd", "BAN"), "Bhutan": ("Bután", "bt", "BHU"), "Brunei": ("Brunéi", "bn", "BRU"),
    "Cambodia": ("Camboya", "kh", "CAM"), "China PR": ("China", "cn", "CHN"), "Guam": ("Guam", "gu", "GUM"),
    "Hong Kong": ("Hong Kong", "hk", "HKG"), "India": ("India", "in", "IND"), "Indonesia": ("Indonesia", "id", "IDN"),
    "Iran": ("Irán", "ir", "IRN"), "Iraq": ("Irak", "iq", "IRQ"), "Japan": ("Japón", "jp", "JPN"), "Jordan": ("Jordania", "jo", "JOR"),
    "Kuwait": ("Kuwait", "kw", "KUW"), "Kyrgyzstan": ("Kirguistán", "kg", "KGZ"), "Laos": ("Laos", "la", "LAO"),
    "Lebanon": ("Líbano", "lb", "LIB"), "Macau": ("Macao", "mo", "MAC"), "Malaysia": ("Malasia", "my", "MAS"),
    "Maldives": ("Maldivas", "mv", "MDV"), "Mongolia": ("Mongolia", "mn", "MNG"), "Myanmar": ("Birmania", "mm", "MYA"),
    "Nepal": ("Nepal", "np", "NEP"), "North Korea": ("Corea del Norte", "kp", "PRK"), "Oman": ("Omán", "om", "OMA"),
    "Pakistan": ("Pakistán", "pk", "PAK"), "Palestine": ("Palestina", "ps", "PLE"), "Philippines": ("Filipinas", "ph", "PHI"),
    "Qatar": ("Catar", "qa", "QAT"), "Saudi Arabia": ("Arabia Saudita", "sa", "KSA"), "Singapore": ("Singapur", "sg", "SGP"),
    "South Korea": ("Corea del Sur", "kr", "KOR"), "Sri Lanka": ("Sri Lanka", "lk", "SRI"), "Syria": ("Siria", "sy", "SYR"),
    "Taiwan": ("Taiwán", "tw", "TPE"), "Tajikistan": ("Tayikistán", "tj", "TJK"), "Thailand": ("Tailandia", "th", "THA"),
    "Timor-Leste": ("Timor Oriental", "tl", "TLS"), "Turkmenistan": ("Turkmenistán", "tm", "TKM"),
    "United Arab Emirates": ("Emiratos Árabes Unidos", "ae", "UAE"), "Uzbekistan": ("Uzbekistán", "uz", "UZB"),
    "Vietnam": ("Vietnam", "vn", "VIE"), "Yemen": ("Yemen", "ye", "YEM"),
    # --- Oceanía (OFC)
    "New Zealand": ("Nueva Zelanda", "nz", "NZL"), "Fiji": ("Fiyi", "fj", "FIJ"), "Papua New Guinea": ("Papúa Nueva Guinea", "pg", "PNG"),
    "Solomon Islands": ("Islas Salomón", "sb", "SOL"), "Vanuatu": ("Vanuatu", "vu", "VAN"),
    "New Caledonia": ("Nueva Caledonia", "nc", "NCL"), "Tahiti": ("Tahití", "pf", "TAH"), "Samoa": ("Samoa", "ws", "SAM"),
    "Tonga": ("Tonga", "to", "TGA"), "Cook Islands": ("Islas Cook", "ck", "COK"), "American Samoa": ("Samoa Americana", "as", "ASA"),
}
_POR_ES = {v[0]: v for v in PAISES.values()}
URL_BANDERA = "https://flagcdn.com/w160/{iso}.png"


def nombre(en: str) -> str:
    """Nombre en español (si no está en la tabla, el original)."""
    return PAISES.get(en, (en,))[0]


def bandera(es: str):
    """URL de la bandera de la selección (nombre ya en español) o None si no está en la tabla."""
    v = _POR_ES.get(es)
    return URL_BANDERA.format(iso=v[1]) if v else None


def codigo(es: str):
    """Código de tres letras (ARG, BRA...) o None si no está en la tabla."""
    v = _POR_ES.get(es)
    return v[2] if v else None
