"""Confederación (región) de cada selección nacional, para separarlas en Líneas de equipos.

Las claves son los nombres en inglés que usa el CSV de martj42/international_results (antes de traducirlos).
Cualquier selección que no esté aquí (equipos regionales, CONIFA, etc.) queda en «Otras selecciones».
"""
from common import normalizar

SUDAMERICA = "🌎 Sudamérica"
EUROPA = "🌍 Europa"
NORTE_CENTRO = "🌎 Norte y Centroamérica"
AFRICA = "🌍 África"
ASIA = "🌏 Asia"
OCEANIA = "🌊 Oceanía"
OTRAS = "🏳️ Otras selecciones"
ORDEN = [SUDAMERICA, EUROPA, NORTE_CENTRO, AFRICA, ASIA, OCEANIA, OTRAS]

_LISTAS = {
    SUDAMERICA: "Argentina, Bolivia, Brazil, Chile, Colombia, Ecuador, Paraguay, Peru, Uruguay, Venezuela",
    EUROPA: "Albania, Andorra, Armenia, Austria, Azerbaijan, Belarus, Belgium, Bosnia and Herzegovina, Bulgaria, Croatia, "
            "Cyprus, Czech Republic, Czechia, Denmark, England, Estonia, Faroe Islands, Finland, France, Georgia, Germany, "
            "Gibraltar, Greece, Hungary, Iceland, Israel, Italy, Kazakhstan, Kosovo, Latvia, Liechtenstein, Lithuania, "
            "Luxembourg, Malta, Moldova, Montenegro, Netherlands, North Macedonia, Macedonia, Northern Ireland, Norway, "
            "Poland, Portugal, Republic of Ireland, Ireland, Romania, Russia, San Marino, Scotland, Serbia, Slovakia, "
            "Slovenia, Spain, Sweden, Switzerland, Turkey, Turkiye, Ukraine, Wales",
    NORTE_CENTRO: "Anguilla, Antigua and Barbuda, Aruba, Bahamas, Barbados, Belize, Bermuda, British Virgin Islands, Canada, "
                  "Cayman Islands, Costa Rica, Cuba, Curacao, Dominica, Dominican Republic, El Salvador, French Guiana, Grenada, "
                  "Guadeloupe, Guatemala, Guyana, Haiti, Honduras, Jamaica, Martinique, Mexico, Montserrat, Nicaragua, Panama, "
                  "Puerto Rico, Saint Kitts and Nevis, Saint Lucia, Saint Martin, Saint Vincent and the Grenadines, Sint Maarten, "
                  "Bonaire, Suriname, Trinidad and Tobago, Turks and Caicos Islands, United States, United States Virgin Islands",
    AFRICA: "Algeria, Angola, Benin, Botswana, Burkina Faso, Burundi, Cameroon, Cape Verde, Cabo Verde, Central African Republic, "
            "Chad, Comoros, Congo, DR Congo, Congo DR, Djibouti, Egypt, Equatorial Guinea, Eritrea, Eswatini, Swaziland, Ethiopia, "
            "Gabon, Gambia, Ghana, Guinea, Guinea-Bissau, Ivory Coast, Cote d'Ivoire, Kenya, Lesotho, Liberia, Libya, Madagascar, "
            "Malawi, Mali, Mauritania, Mauritius, Morocco, Mozambique, Namibia, Niger, Nigeria, Rwanda, Sao Tome and Principe, "
            "Senegal, Seychelles, Sierra Leone, Somalia, South Africa, South Sudan, Sudan, Tanzania, Togo, Tunisia, Uganda, "
            "Zambia, Zimbabwe",
    ASIA: "Afghanistan, Australia, Bahrain, Bangladesh, Bhutan, Brunei, Cambodia, China PR, China, Guam, Hong Kong, India, "
          "Indonesia, Iran, Iraq, Japan, Jordan, Kuwait, Kyrgyzstan, Laos, Lebanon, Macau, Malaysia, Maldives, Mongolia, Myanmar, "
          "Burma, Nepal, North Korea, Northern Mariana Islands, Oman, Pakistan, Palestine, Philippines, Qatar, Saudi Arabia, "
          "Singapore, South Korea, Korea Republic, Sri Lanka, Syria, Taiwan, Tajikistan, Thailand, Timor-Leste, East Timor, "
          "Turkmenistan, United Arab Emirates, Uzbekistan, Vietnam, Yemen",
    OCEANIA: "American Samoa, Cook Islands, Fiji, New Caledonia, New Zealand, Papua New Guinea, Samoa, Solomon Islands, Tahiti, "
             "Tonga, Vanuatu",
}
_CONF = {normalizar(n.strip()): conf for conf, lista in _LISTAS.items() for n in lista.split(",")}


def de(nombre_en_ingles) -> str:
    """Confederación de una selección (nombre en inglés, como viene en el CSV). OTRAS si no se reconoce."""
    return _CONF.get(normalizar(nombre_en_ingles), OTRAS)
