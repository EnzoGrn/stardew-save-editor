"""Calendar and weather: the date in every place the game keeps it, tomorrow's weather.

The mini-save is on winter 21 of year 2, with a host and a farmhand at that date
and a farmhand who last played on summer 14.
"""
import pytest

from sdvsave import SaveError, SaveGame, xmlio

XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"


def farmer(uid, name, day, season, year, played):
    return (f"<name>{name}</name><dayOfMonthForSaveGame>{day}</dayOfMonthForSaveGame>"
            f"<seasonForSaveGame>{season}</seasonForSaveGame><yearForSaveGame>{year}</yearForSaveGame>"
            f"<stats><daysPlayed /><Values><item><key><string>daysPlayed</string></key>"
            f"<value><unsignedInt>{played}</unsignedInt></value></item></Values></stats>"
            f"<UniqueMultiplayerID>{uid}</UniqueMultiplayerID>")


def weather(context, tomorrow):
    return (f"<item><key><string>{context}</string></key><value><LocationWeather>"
            f"<weatherForTomorrow><string>{tomorrow}</string></weatherForTomorrow><weather><string>Sun</string></weather>"
            f"<WeatherForTomorrow>{tomorrow}</WeatherForTomorrow><Weather>Sun</Weather></LocationWeather></value></item>")


def write_save(folder):
    folder.mkdir()
    host = farmer("-123", "Host", 21, 3, 2, 217)
    (folder / folder.name).write_text(
        f'<SaveGame xmlns:xsi="{XSI_NS}"><player>{host}</player><currentSeason>winter</currentSeason>'
        "<dayOfMonth>21</dayOfMonth><year>2</year><locationWeather>"
        + weather("Default", "Sun") + weather("Island", "Sun") + weather("Desert", "Sun")
        + "</locationWeather><weatherForTomorrow>Sun</weatherForTomorrow><farmhands>"
        f"<Farmer>{farmer('1', 'Here', 21, 3, 2, 217)}</Farmer>"
        f"<Farmer>{farmer('2', 'Away', 14, 1, 2, 154)}</Farmer></farmhands></SaveGame>", encoding="utf-8")
    (folder / "SaveGameInfo").write_text(f'<Farmer xmlns:xsi="{XSI_NS}">{host}</Farmer>', encoding="utf-8")
    return folder


@pytest.fixture
def save(tmp_path):
    return SaveGame(write_save(tmp_path / "Test_1"))


def dates(save):
    """(day, season, year, days played) of each farmer, then of SaveGameInfo."""
    farmers = [el for el, _ in save._farmers()] + [save.info.getroot()]
    return [(f.findtext("dayOfMonthForSaveGame"), f.findtext("seasonForSaveGame"), f.findtext("yearForSaveGame"),
             save._days_played(f).text) for f in farmers]


def test_calendar(save):
    assert save.calendar() == {"season": "winter", "day": 21, "year": 2,
                               "weather_tomorrow": {"Default": "Sun", "Island": "Sun"}}  # no desert


def test_moving_forward_into_a_new_year(save):
    assert save.set_date("spring", 1, 3) == 8
    root = save.root
    assert (root.findtext("currentSeason"), root.findtext("dayOfMonth"), root.findtext("year")) == ("spring", "1", "3")
    host, here, away, info = dates(save)
    assert host == here == info == ("1", "0", "3", "225")    # (3 - 1) × 112 + 1
    assert away == ("14", "1", "2", "154")                   # away since summer: untouched


def test_going_back_never_drops_below_one_day(save):
    assert save.set_date("spring", 1, 1) == 1 - 217
    assert dates(save)[0] == ("1", "0", "1", "1")


@pytest.mark.parametrize("season, day, year, key", [
    ("autumn", 1, 1, "error.bad_choice"),
    ("fall", 29, 1, "error.out_of_range"),
    ("fall", 0, 1, "error.out_of_range"),
    ("fall", 1, 0, "error.out_of_range"),
])
def test_invalid_dates_are_refused(save, season, day, year, key):
    with pytest.raises(SaveError) as error:
        save.set_date(season, day, year)
    assert error.value.key == key


def test_weather_tomorrow_everywhere_it_is_written(save):
    save.set_weather_tomorrow("Default", "Storm")
    save.set_weather_tomorrow("Island", "Rain")
    assert save.calendar()["weather_tomorrow"] == {"Default": "Storm", "Island": "Rain"}
    assert save.root.findtext("weatherForTomorrow") == "Storm"
    valley = save._weather_contexts()["Default"]
    assert (valley.findtext("weatherForTomorrow/string"), valley.findtext("WeatherForTomorrow")) == ("Storm", "Storm")


@pytest.mark.parametrize("context, value", [("Island", "Snow"), ("Default", "Hail"), ("Desert", "Rain")])
def test_invalid_weather_is_refused(save, context, value):
    with pytest.raises(SaveError) as error:
        save.set_weather_tomorrow(context, value)
    assert error.value.key == "error.bad_choice"


def test_calendar_survives_writing_and_reading(save, tmp_path):
    save.set_date("summer", 5, 2)
    save.set_weather_tomorrow("Default", "Rain")
    save.write()
    again = SaveGame(tmp_path / "Test_1")
    assert again.calendar() == {"season": "summer", "day": 5, "year": 2,
                                "weather_tomorrow": {"Default": "Rain", "Island": "Sun"}}
    assert b"<daysPlayed />" in xmlio.serialize(again.main)  # the old empty field stays as it was