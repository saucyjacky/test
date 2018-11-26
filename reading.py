import tournament
import asyncio
from fuzzywuzzy import fuzz
import quizdb


async def read_nums(bot, question_arr, sent_question, event):
    try:
        j = 0
        for i in range(1, question_arr.__len__() // 5 + 1):
            if not event.is_set():
                sent_question_content = sent_question.content
                sent_question = await bot.edit_message(sent_question,
                                                       sent_question_content + " :bell:")
            await event.wait()  # will block if a buzz is in progress
            sent_question_content = sent_question.content
            sent_question = await bot.edit_message(sent_question,
                                                   sent_question_content + " " + " ".join(
                                                       question_arr[i * 5:i * 5 + 5]))
            j = i
            await asyncio.sleep(1)
        for i in range(0, 10):
            if not event.is_set():
                sent_question_content = sent_question.content
                sent_question = await bot.edit_message(sent_question,
                                                       sent_question_content + " :bell:")
            await event.wait()
            await asyncio.sleep(0.5)
    except asyncio.CancelledError:
        print("buzzed")
    finally:
        print("done reading")
        sent_question_content = sent_question.content
        await bot.edit_message(sent_question, sent_question_content + " " + " ".join(question_arr[j * 5 + 5:]))
        # edit question to full

        return 1

async def get_buzz(bot, event, channel, check):
    try:
        await asyncio.sleep(1)
        msg = await bot.wait_for_message(channel=channel, check=check)
        if "skip" in msg.content:
            return msg
        event.clear()  # pause
        print("buzzed")
        await bot.send_message(channel, f"buzz from {msg.author}! 10 seconds to answer")
        answer = await bot.wait_for_message(timeout=10, author=msg.author)
        return answer
    except asyncio.CancelledError:
        return None


async def timeout(buzz, reading):
    while not reading.done():
        await asyncio.sleep(0.5)
    buzz.cancel()

async def read_question(bot, bonus=False, playerlist=None, ms=False, category=None):
    # print([str(player) for player in playerlist])
    correct = False
    skip = False
    if not ms:
        question_obj = quizdb.get_tossups(category)
    else:
        question_obj = quizdb.get_ms()
    print(f'question from {question_obj.packet}, answer {question_obj.formatted_answer}')
    neggers = []
    print(question_obj.category)
    question_arr = question_obj.text.split(" ")
    sent_question = await bot.say(" ".join(question_arr[:5]))
    print(sent_question.channel)
    await asyncio.sleep(1)
    i = 0
    event = asyncio.Event()
    event.set()
    loop = asyncio.get_event_loop()

    def check(message):
        if not playerlist:
            return message.author not in neggers and (
            "buzz" in message.content.lower() or "skip" in message.content.lower())
        return tournament.get_player(message.author,
                                     message.server) in playerlist and message.author not in neggers and "buzz" in message.content.lower()

    buzz = loop.create_task(get_buzz(bot, event, sent_question.channel, check))
    reading = loop.create_task(read_nums(bot, question_arr, sent_question, event))

    while not reading.done():
        loop.create_task(timeout(buzz, reading))
        buzz = await buzz
        if not buzz:
            break
        if "skip" in buzz.content:
            if not reading.done():
                reading.cancel()
            skip = True
            break
        matched = match(buzz.content, question_obj.formatted_answer, "</" in question_obj.formatted_answer)
        if matched == "p":
            await bot.say("prompt")
            answer = await bot.wait_for_message(timeout=10, author=buzz.author)
            matched = match(answer.content, question_obj.formatted_answer,
                            "</" in question_obj.formatted_answer, is_prompt=True)
        if matched == "y":
            reading.cancel()
            await bot.say("correct!")
            await print_answer(bot, question_obj.formatted_answer, True)
            correct = True
            if playerlist:
                team = tournament.get_team(buzz.author, buzz.author.server)
                player = tournament.get_player(buzz.author, buzz.author.server)
                team.score += 20
                player.score += 20
        else:
            await bot.say("incorrect!")
            neggers.append(buzz.author)
            event.set()
            await asyncio.sleep(0.75)

    if not correct:
        await print_answer(bot, question_obj.formatted_answer, True)

    print("finished reading")
    if correct and bonus:
        await read_bonus(bot, buzz.author, team)
    neggers.clear()
    msg = await bot.wait_for_message(timeout=20, content="n")
    if msg is not None:
        await read_question(bot, ms=ms, category=category)


def match(given, answer, formatted, is_prompt=False):
    strong = []
    i = 0
    marker = 0
    tag = False
    prompt = False
    if formatted:  # woohoo!
        answer = answer.replace("<u>", "").replace("</u>", "").replace("<em>", "").replace("</em", "")
        while i < len(answer):
            if answer[i] == '<' and (answer[i + 1:i + 7] == "strong" or answer[i + 1:i + 3] == "em") and not tag:
                # found tag
                tag = True
                while answer[i] != '>':
                    i += 1
                i += 1
                marker = i
            # now in strong portion
            if answer[i] == '<' and (answer[i + 1:i + 8] == "/strong" or answer[i + 1:i + 4] == "/em") and tag:
                strong.append(answer[marker:i])
                tag = False
            i += 1

        for bold in strong:
            num_words = len(bold.split(" "))
            print("length", num_words)
            for i in range(0, len(given.split(" ")) - num_words + 1):
                phrase = " ".join(given.split(" ")[i:i + num_words])
                ratio = fuzz.ratio(phrase.lower(), bold.lower())
                print(bold, phrase, ratio)
                if ratio > 75:
                    return "y"
                if ratio > 55:
                    prompt = True
        if not is_prompt and prompt:
            return "p"
        else:
            return "n"
    else:
        answers = answer.replace("The", "").split(" ")
        givens = given.split(" ")
        prompt = False
        for word in answers:
            for w in givens:
                ratio = fuzz.ratio(w.lower(), word.lower())
                print(ratio)
                if ratio > 80:
                    return "y"
                if ratio > 55:
                    prompt = True
        if not is_prompt and prompt:
            return "p"
        return "n"


async def print_answer(bot, answer: str, formatted):
    if not formatted:
        await bot.say(answer)
        return
    i = 0
    answer = answer.replace("<u>", "").replace("</u>", "")
    strongtag = False
    emtag = False
    printme = ""
    while i < len(answer):
        if answer[i] == '<' and answer[i + 1:i + 7] == "strong" and not strongtag:
            strongtag = True
            while answer[i] != '>':
                i += 1
            printme += "**"
        elif answer[i] == '<' and answer[i + 1:i + 3] == "em" and not emtag:
            emtag = True
            while answer[i] != '>':
                i += 1
            if len(printme) >= 2 and printme[len(printme) - 2] == '*':
                printme += " *"
            else:
                printme += "*"
        elif answer[i] == '<' and answer[i + 1:i + 8] == "/strong" and strongtag:
            strongtag = False
            while answer[i] != '>':
                i += 1
            printme += "**"
        elif answer[i] == '<' and answer[i + 1:i + 4] == "/em" and emtag:
            emtag = False
            while answer[i] != '>':
                i += 1
            printme += "*"
        else:
            if answer[i] == '<':
                break
            printme += answer[i]
        i += 1
    await bot.say(printme)


async def read_bonus(bot, author, team=None):
    print(author)
    print(author.name)

    bonus_obj = quizdb.get_bonuses()
    print(bonus_obj.formatted_answers[0])
    if team:
        await bot.say(f"Bonus for {team.name}:")
        await asyncio.sleep(1)
    if bonus_obj.leadin == "[missing]":
        bonus_obj.leadin = "For 10 points each:"
    question_arr = bonus_obj.leadin.split(" ")
    sent_question = await bot.say(" ".join(question_arr[:5]))
    await asyncio.sleep(1)
    for i in range(1, len(question_arr) // 5 + 1):
        sent_question_content = sent_question.content
        sent_question = await bot.edit_message(sent_question,
                                               sent_question_content + " " + " ".join(question_arr[i * 5:i * 5 + 5]))
        print(sent_question.content)
        await asyncio.sleep(1)

    # leadin done
    def check(message):
        if not team:
            return message.author == author
        return tournament.get_player(message.author, message.server) in team.members

    for j in range(0, 3):
        correct = False
        question_arr = bonus_obj.texts[j].split(" ")
        formatted = bonus_obj.formatted_answers[j]
        sent_question = await bot.say(" ".join(question_arr[:5]))
        await asyncio.sleep(1)
        for i in range(1, len(question_arr) // 5 + 1):
            sent_question_content = sent_question.content
            sent_question = await bot.edit_message(sent_question,
                                                   sent_question_content + " " + " ".join(question_arr[i * 5:i * 5 + 5]))
            await asyncio.sleep(1)

        msg = None
        msg = await bot.wait_for_message(timeout=10, check=check)
        if msg is not None:
            matched = match(msg.content, formatted,
                            "</" in formatted)
            if matched == "p":
                await bot.say("prompt")
                answer = await bot.wait_for_message(timeout=10, author=msg.author)
                matched = match(answer.content, formatted, "</" in formatted, is_prompt=True)
            if matched == "y":
                await bot.say("correct!")
                await print_answer(bot, formatted, "</" in formatted)
                correct = True
                if team:
                    team = tournament.get_team(msg.author, msg.author.server)
                    player = tournament.get_player(msg.author, msg.author.server)
                    team.score += 10
                    player.score += 10
            else:
                await bot.say("incorrect!")
                print("incorrect")
        else:
            await bot.say("Time's up!")
            await asyncio.sleep(1)
        if not correct:
            await print_answer(bot, bonus_obj.formatted_answers[j], "</" in formatted)
