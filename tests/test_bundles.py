"""Community Center: bundle progress, completing and resetting bundles.

The mini-save has a Pantry with two bundles (one done, one empty) and a restored
Vault. Each bundle keeps one flag per ingredient token, like real saves.
"""
import pytest

from sdvsave import SaveError, SaveGame, xmlio

XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"


def flags(*values):
    return "<ArrayOfBoolean>" + "".join(f"<boolean>{'true' if v else 'false'}</boolean>" for v in values) + "</ArrayOfBoolean>"


def entry(key_tag, key, value):
    return f"<item><key><{key_tag}>{key}</{key_tag}></key><value>{value}</value></item>"


def write_save(folder, joja=False):
    folder.mkdir()
    mail = "<mailReceived><string>ccVault</string>" + ("<string>JojaMember</string>" if joja else "") + "</mailReceived>"
    farmer = f"<name>Host</name>{mail}<UniqueMultiplayerID>-123</UniqueMultiplayerID>"
    bundle_data = (entry("string", "Pantry/0", "<string>Spring Crops/O 465 20/24 1 0 188 1 0/0///Récoltes de printemps</string>")
                   + entry("string", "Pantry/3", "<string>Quality Crops/BO 15 1/24 5 2 254 5 2 276 5 2/6/2//Récoltes de qualité</string>")
                   + entry("string", "Vault/23", "<string>2,500g/O 220 3/-1 2500 2500/4/</string>"))
    cc = ("<GameLocation xsi:type=\"CommunityCenter\"><name>CommunityCenter</name><areasComplete>"
          + "".join(f"<boolean>{'true' if i == 4 else 'false'}</boolean>" for i in range(6)) + "</areasComplete><bundles>"
          + entry("int", 0, flags(*[True] * 6)) + entry("int", 3, flags(*[False] * 9)) + entry("int", 23, flags(True, False, False))
          + "</bundles><bundleRewards>"
          + entry("int", 0, "<boolean>false</boolean>") + entry("int", 3, "<boolean>false</boolean>")
          + entry("int", 23, "<boolean>false</boolean>") + "</bundleRewards></GameLocation>")
    (folder / folder.name).write_text(
        f'<SaveGame xmlns:xsi="{XSI_NS}"><player>{farmer}</player><locations>{cc}</locations>'
        f"<bundleData>{bundle_data}</bundleData><farmhands /></SaveGame>", encoding="utf-8")
    (folder / "SaveGameInfo").write_text(f'<Farmer xmlns:xsi="{XSI_NS}">{farmer}</Farmer>', encoding="utf-8")
    return folder


@pytest.fixture
def save(tmp_path):
    return SaveGame(write_save(tmp_path / "Test_1"))


def bundle(save, bundle_id):
    return save._bundle(bundle_id)[1]


def host_mail(save):
    return [[m.text for m in mail] for mail in save._host_mail()]


def test_progress(save):
    rooms = {r["room"]: r for r in save.community_center()["rooms"]}
    assert (rooms["Pantry"]["area"], rooms["Pantry"]["restored"], rooms["Vault"]["restored"]) == (0, False, True)
    spring, quality = rooms["Pantry"]["bundles"]
    assert (spring["display"], spring["complete"], spring["given"], spring["need"]) == ("Récoltes de printemps", True, 2, 2)
    assert (quality["complete"], quality["need"], len(quality["ingredients"])) == (False, 2, 3)  # 2 of 3
    assert quality["ingredients"][0] == {"item_id": "24", "count": 5, "quality": 2, "donated": False}
    assert bundle(save, 23)["complete"]  # gold bundle: its first flag is enough


def test_completing_the_last_bundle_restores_the_room(save):
    assert save.complete_bundle(3) is True
    quality = bundle(save, 3)
    assert quality["complete"] and quality["reward_waiting"]
    assert [x.text for x in save._community_center().find("areasComplete")][0] == "true"
    assert host_mail(save) == [["ccVault", "ccPantry"]] * 2   # save and SaveGameInfo


def test_completing_a_complete_bundle_changes_nothing(save):
    assert save.complete_bundle(0) is False
    assert host_mail(save) == [["ccVault"]] * 2


def test_reset(save):
    save.reset_bundle(0)
    spring = bundle(save, 0)
    assert (spring["given"], spring["complete"], spring["reward_waiting"]) == (0, False, False)


def test_restored_room_cant_be_reset(save):
    with pytest.raises(SaveError) as error:
        save.reset_bundle(23)
    assert error.value.key == "error.room_restored"


def test_joja_farm_is_read_only(tmp_path):
    save = SaveGame(write_save(tmp_path / "Joja_1", joja=True))
    assert save.community_center()["joja"]
    with pytest.raises(SaveError) as error:
        save.complete_bundle(3)
    assert error.value.key == "error.bundle_locked"


def test_unknown_bundle(save):
    with pytest.raises(SaveError) as error:
        save.complete_bundle(99)
    assert error.value.key == "error.no_bundle"


def test_bundles_survive_writing_and_reading(save, tmp_path):
    save.complete_bundle(3)
    save.write()
    again = SaveGame(tmp_path / "Test_1")
    assert bundle(again, 3)["complete"]
    assert b"<string>ccPantry</string>" in xmlio.serialize(again.main)