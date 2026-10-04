"""Quests: the journal of each farmer, completing and removing quests."""
import pytest

from sdvsave import SaveError, SaveGame, xmlio

XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"


def quest(kind, title, quest_id, reward, cancellable=True, extra=""):
    return (f'<Quest xsi:type="{kind}"><_currentObjective /><_questDescription /><_questTitle>{title}</_questTitle>'
            f"<completed>false</completed><dailyQuest>false</dailyQuest><showNew>false</showNew>"
            f"<canBeCancelled>{'true' if cancellable else 'false'}</canBeCancelled><id>{quest_id}</id>"
            f"<moneyReward>{reward}</moneyReward><daysLeft>0</daysLeft><questTitle>{title}</questTitle>{extra}</Quest>")


def write_save(folder):
    folder.mkdir()
    log = ("<questLog>" + quest("ItemDeliveryQuest", "Pêcher un calmar", 109, 800,
                                extra="<target>Willy</target><item>(O)151</item><number>1</number>")
           + quest("Quest", "Introductions", 9, 0, cancellable=False) + "</questLog>")
    farmer = f"<name>Host</name>{log}<UniqueMultiplayerID>-123</UniqueMultiplayerID>"
    (folder / folder.name).write_text(
        f'<SaveGame xmlns:xsi="{XSI_NS}"><player>{farmer}</player><farmhands /></SaveGame>', encoding="utf-8")
    (folder / "SaveGameInfo").write_text(f'<Farmer xmlns:xsi="{XSI_NS}">{farmer}</Farmer>', encoding="utf-8")
    return folder


@pytest.fixture
def save(tmp_path):
    return SaveGame(write_save(tmp_path / "Test_1"))


def test_journal(save):
    delivery, story = save.quests("-123")
    assert (delivery["title"], delivery["type"], delivery["reward"], delivery["completed"]) == \
        ("Pêcher un calmar", "ItemDeliveryQuest", 800, False)
    assert (delivery["target"], delivery["item"], delivery["number"]) == ("Willy", "(O)151", 1)
    assert delivery["cancellable"] and not story["cancellable"]


def test_complete_in_both_files(save):
    assert save.complete_quest("-123", 0) == "Pêcher un calmar"
    for farmer in save._copies("-123"):
        done = farmer.find("questLog")[0]
        assert (done.findtext("completed"), done.findtext("showNew"), done.findtext("moneyReward")) == ("true", "true", "800")


def test_remove_in_both_files(save):
    assert save.remove_quest("-123", 1) == "Introductions"
    for farmer in save._copies("-123"):
        assert [q.findtext("id") for q in farmer.find("questLog")] == ["109"]


def test_unknown_quest(save):
    for action in (save.complete_quest, save.remove_quest):
        with pytest.raises(SaveError) as error:
            action("-123", 5)
        assert error.value.key == "error.no_quest"


def test_quests_survive_writing_and_reading(save, tmp_path):
    save.complete_quest("-123", 0)
    save.write()
    again = SaveGame(tmp_path / "Test_1")
    assert again.quests("-123")[0]["completed"]
    assert b'<Quest xsi:type="ItemDeliveryQuest">' in xmlio.serialize(again.main)