import tournament
import asyncio
from fuzzywuzzy import fuzz
import quizdb
import discord


async def read_tossup(question_obj, channel, event):
    question_arr = question_obj.text.split(" ")
    power = False
    try:
        sent_question = await channel.send(" ".join(question_arr[:5]))
        await asyncio.sleep(1)
        j = 0
        buzz = False
        for i in range(1, len(question_arr) // 5 + 1):
            if event.negged:
                print("negged!")
            if not event.is_set():
                buzz = True
                sent_question_content = sent_question.content
                await sent_question.edit(content=sent_question_content + " :bell:")
            await event.wait()  # will block if a buzz is in progress
            if buzz:
                buzz = False
                sent_question = await channel.send(sent_question.content.replace(" :bell:", " :no_bell:"))
                event.negged = False
                await asyncio.sleep(1)
            sent_question_content = sent_question.content
            await sent_question.edit(content=sent_question_content + " " + " ".join(question_arr[i * 5:i * 5 + 5]))
            j = i
            await asyncio.sleep(1)
        event.over = True
        for i in range(0, 10):
            await asyncio.sleep(0.5)
            if not event.is_set():
                sent_question_content = sent_question.content
                await sent_question.edit(content=sent_question_content + " :bell:")
            await event.wait()

    except asyncio.CancelledError:
        print("canceled")
    finally:
        print("done reading")
        sent_question_content = sent_question.content
        if "(*)" not in sent_question_content and question_obj.power:
            power = True
        await sent_question.edit(content=sent_question_content + " " + " ".join(question_arr[j * 5 + 5:]))
        # edit question to full
        return power


async def wait_for_buzz(bot, event, channel, check):
    try:
        msg = await bot.wait_for('message', check=check)
        if "skip" in msg.content:
            return msg
        event.clear()  # pause
        await channel.send(f"buzz from {msg.author.mention}! 10 seconds to answer")
        try:
            answer = await bot.wait_for('message', timeout=10.0, check=lambda x: x.author == msg.author)
        except asyncio.TimeoutError as e:
            return msg.author
        return answer
    except asyncio.CancelledError:
        return None


async def timeout(buzz, reading):
    await reading
    if not buzz.done():
        buzz.cancel()


async def tossup(bot, channel, is_bonus=False, playerlist=None, ms=False, category=None):
    correct = False
    if not ms:
        question_obj = await bot.db.get_tossups(category)
    else:
        question_obj = await bot.db.get_ms()
    print(f'question from {question_obj.packet}, answer {question_obj.formatted_answer}')
    neg_list = []
    print(f'theme: {question_obj.category}, power={question_obj.power}')
    event = asyncio.Event()
    event.set()
    event.negged = False
    event.over = False
    loop = asyncio.get_event_loop()

    def check(message):
        if message.channel != channel:
            return False
        if not playerlist:
            return message.author not in neg_list and (
                    message.content.lower() == "buzz" or message.content.lower() == "skip")
        return tournament.get_player(message.author, message.guild) in playerlist and message.author not in neg_list \
               and message.content.lower() == "buzz"

    buzz = loop.create_task(wait_for_buzz(bot, event, channel, check))
    reading = loop.create_task(read_tossup(question_obj, channel, event))

    while not reading.done():
        loop.create_task(timeout(buzz, reading))
        answer = await buzz
        if not answer:
            break
        if isinstance(answer, discord.Member):
            buzz = loop.create_task(wait_for_buzz(bot, event, channel, check))
            await channel.send("No answer!")
            neg_list.append(answer)
            event.set()
            continue

        if "skip" == answer.content:
            if not reading.done():
                reading.cancel()
                buzz.cancel()
            break

        matched = match(answer.content, question_obj.formatted_answer, "</strong" in question_obj.formatted_answer)
        if matched == "p":
            await channel.send("prompt")
            try:
                answer = await bot.wait_for('message', timeout=10, check=lambda x: x.author == answer.author)
                matched = match(answer.content, question_obj.formatted_answer,
                                "</strong" in question_obj.formatted_answer, is_prompt=True)
            except asyncio.TimeoutError:
                matched = "n"

        if matched == "y":
            reading.cancel()
            power = await reading
            if power:
                await channel.send("correct - power!")
            else:
                await channel.send("correct!")
            await print_answer(channel, question_obj.formatted_answer, True)
            correct = True
            if playerlist:
                team = tournament.get_team(answer.author, answer.guild)
                player = tournament.get_player(answer.author, answer.guild)
                if power:
                    team.score += 15
                    player.score += 15
                else:
                    team.score += 10
                    player.score += 10
        else:
            buzz = loop.create_task(wait_for_buzz(bot, event, channel, check))
            await channel.send("incorrect!")
            neg_list.append(answer.author)
            event.set()
            event.negged = True
            if not event.over and playerlist:
                team = tournament.get_team(answer.author, answer.guild)
                player = tournament.get_player(answer.author, answer.guild)
                team.score -= 5
                player.score -= 5
            await asyncio.sleep(0.75)

    if not correct:
        await channel.send("Time's up!")
        await print_answer(channel, question_obj.formatted_answer, True)

    if correct and is_bonus:
        ctx = await bot.get_context(answer)
        await bonus(bot, ctx, team)
    neg_list.clear()
    if not playerlist:
        try:
            await bot.wait_for('message', timeout=20, check=lambda x: x.content == 'n' and x.channel == channel)
            await tossup(bot, channel, ms=ms, category=category)
        except asyncio.TimeoutError:
            pass


def match(given, answer, formatted, is_prompt=False):
    strong = []
    i = 0
    marker = 0
    tag = False
    prompt = False
    if formatted:  # woohoo!
        answer = answer.replace("<u>", "").replace("</u>", "").replace("<em>", "").replace("</em>", "")
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
                strong.append(answer[marker:i].strip())
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
        answer = answer.replace("<em>", "").replace("</em>", "")
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


async def print_answer(channel, answer: str, formatted):
    if not formatted:
        await channel.send(answer)
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
    await channel.send(printme)


async def bonus(bot, ctx, team=None):
    bonus_obj = quizdb.get_bonuses()
    print(bonus_obj.formatted_answers[0])
    if team:
        await ctx.send(f"Bonus for {team.name}:")
        await asyncio.sleep(1)
    if bonus_obj.leadin == "[missing]":
        bonus_obj.leadin = "For 10 points each:"
    question_arr = bonus_obj.leadin.split(" ")
    sent_question = await ctx.send(" ".join(question_arr[:5]))
    await asyncio.sleep(1)
    for i in range(1, len(question_arr) // 5 + 1):
        sent_question_content = sent_question.content
        await sent_question.edit(content=sent_question_content + " " + " ".join(question_arr[i * 5:i * 5 + 5]))
        print(sent_question.content)
        await asyncio.sleep(1)

    # leadin done
    def check(message):
        if not team:
            return message.author == ctx.author
        return tournament.get_player(message.author, message.guild) in team.members

    for j in range(0, 3):
        correct = False
        question_arr = bonus_obj.texts[j].split(" ")
        formatted = bonus_obj.formatted_answers[j]
        sent_question = await ctx.send(" ".join(question_arr[:5]))
        await asyncio.sleep(1)
        for i in range(1, len(question_arr) // 5 + 1):
            sent_question_content = sent_question.content
            await sent_question.edit(content=sent_question_content + " " + " ".join(question_arr[i * 5:i * 5 + 5]))
            await asyncio.sleep(1)

        msg = None
        try:
            msg = await bot.wait_for('message', timeout=10, check=check)
            matched = match(msg.content, formatted,
                            "</" in formatted)
            if matched == "p":
                await ctx.send("prompt")
                try:
                    answer = await bot.wait_for('message', timeout=10, check=lambda x: x.author == msg.author)
                    matched = match(answer.content, formatted, "</" in formatted, is_prompt=True)
                except asyncio.TimeoutError:
                    await ctx.send("Time's up!")

            if matched == "y":
                await ctx.send("correct!")
                await print_answer(ctx, formatted, "</" in formatted)
                correct = True
                if team:
                    team = tournament.get_team(msg.author, msg.guild)
                    player = tournament.get_player(msg.author, msg.guild)
                    team.score += 10
                    player.score += 10
            elif matched == "n":
                await ctx.send("incorrect!")
                print("incorrect")
        except asyncio.TimeoutError:
            await ctx.send("Time's up!")
            await asyncio.sleep(1)
        if not correct:
            await print_answer(ctx, bonus_obj.formatted_answers[j], "</" in formatted)
