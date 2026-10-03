"""Translation: French elision of "de" before a name starting with a vowel."""
from web import i18n


def test_french_elides_de_before_a_vowel():
    assert i18n.translate("fr", "chests.home_of", name="Aboobakar") == "Maison d'Aboobakar"
    assert i18n.translate("fr", "chests.home_of", name="Élise") == "Maison d'Élise"
    assert i18n.translate("fr", "chests.home_of", name="Théo") == "Maison de Théo"
    assert i18n.translate("fr", "error.inventory_full", name="Aboobakar") == "L'inventaire d'Aboobakar est plein."


def test_other_languages_are_left_alone():
    assert i18n.translate("en", "chests.home_of", name="Aboobakar") == "Aboobakar's house"