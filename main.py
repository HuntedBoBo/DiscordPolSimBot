import os
import discord
from discord.ext import tasks
import json
import re
import math
import csv
import random
from datetime import datetime, timedelta
from discord import Intents, Client, Message
from discord import app_commands
from dotenv import load_dotenv

# What character to use for commands (must be only 1 character)
prefix = '!'

# What emojis to use for voting (in favor, present, and against in that order)
VOTE_EMOJIS = ['✅', '🟨', '❌']

# How many characters the summary should roughly be
SUM_LEN = 150

# How many hours the vote should last for
VOTE_LEN = 24

# Used as a divider in messages
DIVIDER = '-' * 40

# Load variables from .env file
load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')

ADMIN_ROLE = int(os.getenv('ADMIN_ROLE'))
MOD_ROLE = int(os.getenv('MOD_ROLE'))
SENATOR_ROLE = int(os.getenv('SENATOR_ROLE'))
REP_ROLE = int(os.getenv('REP_ROLE'))
PRESIDENT_ROLE = int(os.getenv('PRESIDENT_ROLE'))
VP_ROLE = int(os.getenv('VP_ROLE'))

NR_ROLE = int(os.getenv('NR_ROLE'))
DEM_ROLE = int(os.getenv('DEM_ROLE'))
CON_ROLE = int(os.getenv('CON_ROLE'))
PDU_ROLE = int(os.getenv('PDU_ROLE'))
IND_ROLE = int(os.getenv('IND_ROLE'))

SENATE_VOTING = int(os.getenv('SENATE_VOTING'))
HOUSE_VOTING = int(os.getenv('HOUSE_VOTING'))
LEGISLATIVE_RECORD = int(os.getenv('LEGISLATIVE_RECORD'))
ELECTION_RESULTS_CHANNEL = int(os.getenv('ELECTION_RESULTS_CHANNEL'))

# Bot setup
intents = Intents.default()
intents.message_content = True
intents.members = True
client = Client(intents=intents)
tree = app_commands.CommandTree(client)

# Is the command tree currently synced?
synced = False

# Keeps track of votes
votes = {
    'votes': []
}

# Load votes from json file
if os.path.isfile('votes.json'):
    votes = json.load(open('votes.json', 'r'))


# Verify if a user has permission to use a restricted command
async def verifyPermission(message):
    # Check if they have an admin or mod role
    roleFound = False
    for role in message.author.roles:
        if role.id == ADMIN_ROLE or role.id == MOD_ROLE:
            roleFound = True
            break

    # Tell the user permission was denied
    if not roleFound:
        await message.reply('Permission denied.')
    
    # Return boolean
    return roleFound

@client.event
async def on_message(message):
    # Ignore the bot's own messages as well as empty messages
    if message.author == client.user or len(message.content) == 0:
        return

    # Check if it's a command
    if message.content[0] == prefix:
        # Split it into 2 parts, the command and the argument(s)
        parts = re.split(r'[\b \b]', message.content, maxsplit=1)
        cmd = parts[0][1:].lower()

        if cmd == 'countmessages':
            if not await verifyPermission(message):
                return

            # Dictionary to keep track of the message count
            messageCount = {}

            # Get a list of every message in that channel
            async for msg in message.channel.history(limit=999):
                # Ignore the bot's own messages and any message that begins with the command prefix
                if msg.author == client.user or len(msg.content) == 0 or msg.content.startswith(prefix):
                    continue

                if msg.author is discord.Member:
                    key = '{} - {}'.format(msg.author.nick, msg.author.name)
                else:
                    key = '{} - {}'.format(msg.author.display_name, msg.author.name)

                if key in messageCount.keys():
                    # Increment the count
                    messageCount[key] += 1
                else:
                    # Create a new entry with a value of one
                    messageCount[key] = 1

            # Build the message to reply with
            reply = ''
            for name in messageCount.keys():
                reply = f'{reply}\n{name}: {messageCount[name]}'

            # Send the reply
            await message.reply(f'```{reply}```')
        elif cmd == 'vote' or cmd == 'votesenate' or cmd == 'votehouse':
            # Check if it's in the correct channel
            if (cmd == 'vote' and message.channel.id in [SENATE_VOTING, HOUSE_VOTING]) or (cmd == 'votesenate' and message.channel.id == SENATE_VOTING) or (cmd == 'votehouse' and message.channel.id == HOUSE_VOTING):
                # Make sure there's actually a message
                if len(parts) >= 2:
                    # Get the end time
                    endTime = datetime.now() + timedelta(hours=VOTE_LEN)
                    timestamp = str(round(endTime.timestamp()))

                    # Send the voting messages
                    messageIDs = {'senate': None, 'house': None}
                    for cid in [SENATE_VOTING, HOUSE_VOTING]:
                        # Skip the house if it's senate-only and skip the senate if it's house-only
                        if (cmd == 'votesenate' and cid != SENATE_VOTING) or (cmd == 'votehouse' and cid != HOUSE_VOTING):
                            continue

                        # Get the role to mention
                        role = SENATOR_ROLE if cid == SENATE_VOTING else REP_ROLE
                        #role = ''

                        # Get the final line of the message
                        finalLine = 'Sponsored by {} | Vote ends <t:{}:R> | <@&{}>'.format(message.author.name, timestamp, role)

                        # Get the channel
                        channel = client.get_channel(cid)

                        # Send the message
                        botMessage = await channel.send('{}\n{}\n{}'.format(parts[1].strip(), DIVIDER, finalLine))

                        # Save the ID
                        messageIDs['senate' if cid == SENATE_VOTING else 'house'] = botMessage.id

                        # Add emojis
                        for emoji in VOTE_EMOJIS:
                            await botMessage.add_reaction(emoji)

                    # Get a summary of the bill to save
                    match = re.search(r"[ \n]", message.content)
                    summary = ''
                    if match:
                        summary = message.content[match.start() + 1:]
                    else:
                        match = message.content
                    if len(summary) > SUM_LEN:
                        words = summary.split(' ')
                        summary = ''
                        chars = 0
                        for word in words:
                            summary += f' {word}'
                            if len(summary) + 1 >= SUM_LEN:
                                break
                        if chars < len(message.content) - 6:
                            summary += '...'
                    summary = summary.strip()

                    # Save the vote to the dictionary
                    votes['votes'].append({
                        'type': 'both' if cmd == 'vote' else 'senate' if cmd == 'votesenate' else 'house',
                        'message_ids': messageIDs,
                        'summary': summary,
                        'end_time': timestamp
                    })

                    # Delete the command message
                    await message.delete()

                    # Save the votes json file (we wait until the end to save it for performance reasons)
                    with open('votes.json', 'w') as f:
                        json.dump(votes, f)
                else:
                    # Tell the user to specify a message
                    await message.reply('Please specify something to vote on.')
            else:
                # It's not in the correct channel
                await message.reply('Incorrect channel.')
        elif cmd == 'chance':
            # Make sure there's a percentage chance
            if len(parts) == 2:
                # Make sure it's a number
                if re.match(r'[^0-9.]', parts[1]):
                    # Tell the user to specify a number
                    await message.reply('The chance must be a number.')
                else:
                    try:
                        # Get the chance as a float
                        chance = float(parts[1]) / 100

                        # Make sure it's within the acceptable range
                        if chance > 1:
                            await message.reply('Maximum chance allowed is 100%.')
                        elif chance < 0:
                            await message.reply('Minimum chance allowed is 0%.')
                        else:
                            # Run the random chance
                            success = random.random() < chance

                            # Tell the user
                            await message.reply(str(success))
                    except ValueError:
                        await message.reply('Chance argument is invalid.')
            elif len(parts) > 2:
                # Tell the user too many arguments were passed
                await message.reply('This command only takes one argument.')
            else:
                # Tell the user to provide a percentage chance
                await message.reply('Please provide a percentage chance. Example: `!chance 50`')
        elif cmd == 'getbp':
            if not await verifyPermission(message):
                return
            await getBP(message)

@client.event
async def on_reaction_add(reaction, user):
    # Ignore the bot's own reactions
    if user == client.user:
        return

    # Get which channel it's in
    channel = reaction.message.channel.id

    # Check if the reaction is in a voting channel
    if channel in [SENATE_VOTING, HOUSE_VOTING]:
        # Get the chamber
        chamber = 'senate' if channel == SENATE_VOTING else 'house'

        # Remove invalid emojis
        if not reaction.emoji in VOTE_EMOJIS:
            await reaction.clear()

        # Remove reaction if the message isn't a bill or voting has ended
        # This is the easiest way to do it without keeping track of every bill forever
        voteFound = None
        for vote in votes['votes']:
            if chamber in vote['message_ids']:
                if vote['message_ids'][chamber] == reaction.message.id:
                    voteFound = vote
                    break

        # Remove reaction if no vote was found
        if voteFound == None:
            await reaction.remove(user)
            return

        # Check if the time has expired yet
        endTime = datetime.fromtimestamp(int(voteFound['end_time']))

        # Remove reaction if the vote has ended
        if endTime <= datetime.now():
            await reaction.remove(user)
            return

        # Remove reactions from people with the wrong role
        valid = False
        for role in user.roles:
            if (role.id == SENATOR_ROLE and channel == SENATE_VOTING) or (role.id == REP_ROLE and channel == HOUSE_VOTING):
                valid = True
                break

        if not valid:
            await reaction.remove(user)
            return

        # Only allow 1 reaction
        for r in reaction.message.reactions:
            # Ignore the reaction that was just added
            if r.emoji == reaction.emoji:
                continue

            # Get the list of users who reacted
            users = [u async for u in r.users()]

            # Iterate through each user
            for u in users:
                if u.id == user.id:
                    # It matches, so remove it
                    await r.remove(user)
                    return

@tasks.loop(minutes=1)
async def hourly():
    global votes

    # A list of votes to remove
    remove = []

    # Automatically check votes once every hour
    for i in range(len(votes['votes'])):
        vote = votes['votes'][i]

        # Check if the time has expired yet
        endTime = datetime.fromtimestamp(int(vote['end_time']))

        # Skip until later if it hasn't
        if endTime > datetime.now():
            continue

        # Whether to skip the vote for now
        skip = False

        # The message to send. Start out with the summary in bold.
        resultsMsg = '**{}**'.format(vote['summary'])

        # Whether the bill had a majority in both chambers (or only one if limited)
        majority = True
        
        # Used for VP stuff
        houseMajority = True
        senateTied = False

        for cid in [SENATE_VOTING, HOUSE_VOTING]:
            # Get whether it's in the house or senate
            chamber = 'senate' if cid == SENATE_VOTING else 'house'

            # Skip incorrect channel
            if (vote['type'] == 'senate' and cid == HOUSE_VOTING) or (vote['type'] == 'house' and cid == SENATE_VOTING):
                continue

            # Get the channel
            channel = client.get_channel(cid)

            # Get the message
            message = None
            try:
                # Get the message
                message = await channel.fetch_message(vote['message_ids'][chamber])

                # Get the votes on it
                votesOnBill = await getVotes(message, chamber)

                # Check if it has a majority
                if votesOnBill[0] <= votesOnBill[2]:
                    majority = False
                    
                    if cid == HOUSE_VOTING:
                        houseMajority = False
                    elif votesOnBill[0] == votesOnBill[2]:
                        senateTied = True

                # Get percentages
                pct = []
                voteSum = sum(votesOnBill)

                if voteSum == 0:
                    # If no one voted, default to 0% to avoid error
                    pct = [0, 0, 0]
                else:
                    for v in votesOnBill:
                        pct.append(round(v / voteSum * 100, 2))

                # Add the results to the message
                resultsMsg = '{}\n{}\n{} Results:\n✅ Yes: {}% ({}) | 🟨 Present: {}% ({}) | ❌ No: {}% ({})\n[Link to bill]({})'.format(resultsMsg, DIVIDER, chamber.title(), pct[0], votesOnBill[0], pct[1], votesOnBill[1], pct[2], votesOnBill[2], message.jump_url)

                # Schedule the vote for removal
                remove.append(i)
            except Exception as e:
                # Print the error
                print(e)

                # Ignore it if the message no longer exists
                remove.append(i)
                skip = True
                break

            # Skip the message if it's empty for whatever reason
            if len(message.content) == 0:
                remove.append(i)
                skip = True
                break

        if skip:
            continue

        # Get the legislative record channel
        recordChannel = client.get_channel(LEGISLATIVE_RECORD)
        
        if majority:
            # Mention the President role if it passed (ignoring supermajority requirements)
            resultsMsg = '{}\n{}\n<@&{}>'.format(resultsMsg, DIVIDER, PRESIDENT_ROLE)
        elif senateTied and houseMajority:
            # Mention the VP role if they need to break a tie in the Senate (only if it passed the house or the house wasn't asked)
            resultsMsg = '{}\n{}\n<@&{}>'.format(resultsMsg, DIVIDER, VP_ROLE)

        # Add a divider to the end
        resultsMsg = '{}\n{}'.format(resultsMsg, DIVIDER)

        # Send the message
        await recordChannel.send(resultsMsg)

    # Remove votes
    
    remove = sorted(list(set(remove)), reverse=True)
    if len(votes['votes']) > 0:
        for i in remove:
            votes['votes'].pop(i)

    # Save any changes to the json file
    with open('votes.json', 'w') as f:
        json.dump(votes, f)

# Return the votes from a message
async def getVotes(message, chamber):
    # Get the list of reactions on the message
    # Order corresponds with VOTE_EMOJIS
    reactions = {}

    for reaction in message.reactions:
        # Check if it's a valid emoji
        if reaction.emoji not in VOTE_EMOJIS:
            # Clear the emoji
            await reaction.clear()
            continue

        users = [user async for user in reaction.users()]

        for user in users:
            member = message.guild.get_member(user.id)

            # Skip the bot's own reactions
            if user == client.user:
                continue

            # Iterate through each user's roles
            valid = False
            party = None

            if member != None:
                for role in member.roles:
                    # Check for chamber-specific role
                    if role.id == (SENATOR_ROLE if chamber == 'senate' else REP_ROLE):
                        valid = True

                    # Check for party role
                    if role.id == DEM_ROLE:
                        party = 'DEM'
                    elif role.id == PDU_ROLE:
                        party = 'PDU'
                    elif role.id == NR_ROLE:
                        party = 'NR'
                    elif role.id == CON_ROLE:
                        party = 'CON'
                    elif role.id == IND_ROLE:
                        party = 'IND'

                    # Break once both have been found
                    if valid and party != None:
                        break

            # Remove reactions from users without the correct role
            if not valid:
                await reaction.remove(user)
                continue

            # If they don't have a party role, default to IND
            if party == None:
                party = 'IND'

            # Count the reaction
            if not party in reactions.keys():
                reactions[party] = [0, 0, 0]
            reactions[party][VOTE_EMOJIS.index(reaction.emoji)] += 1

    # Get the list of seats by party in the respective chamber
    seats = {}

    if os.path.isfile('congress_config.csv'):
        file = open('congress_config.csv', 'r')
        reader = csv.reader(file)
        lines = [row for row in reader]

        for i in range(len(lines[0])):
            if i > 0:
                seats[lines[0][i]] = lines[1 if chamber == 'senate' else 2][i]
    else:
        print('Error: please create congress_config.csv!')
        exit()


    # Get the total number of votes
    totalVotes = [0, 0, 0]

    # Iterate through reactions dict
    for party in reactions.keys():
        # Get the reactions
        partyReact = reactions[party]

        # Get the total number of reactions from that party
        total = sum(partyReact)

        # Get the number of seats for that party
        npcNum = seats[party] - total
        
        # If the total is 0, i.e. no one voted, count every NPC as voting present
        if total == 0:
            totalVotes[1] += npcNum
            continue

        # Add them to the total
        totalVotes[0] += partyReact[0]
        totalVotes[1] += partyReact[1]
        totalVotes[2] += partyReact[2]

        # Get the quotients
        quotients = [npcNum * (partyReact[0] / total), npcNum * (partyReact[1] / total), npcNum * (partyReact[2] / total)]

        # Get the initial allocation
        initial = [math.floor(quotients[0]), math.floor(quotients[1]), math.floor(quotients[2])]

        # Add this to the total
        totalVotes[0] += initial[0]
        totalVotes[1] += initial[1]
        totalVotes[2] += initial[2]

        # Get how many NPCs are left
        npcsLeft = npcNum - sum(initial)

        # Skip the rest if we've already allocated all of the NPCs (unlikely)
        if npcsLeft == 0:
            continue

        # Get the decimals
        decimals = [quotients[0] - initial[0], quotients[1] - initial[1], quotients[2] - initial[2]]

        if npcsLeft == 3:
            # If there's 3 left, give each 1 vote
            totalVotes[0] += 1
            totalVotes[1] += 1
            totalVotes[2] += 1
        elif npcsLeft == 2:
            # If there's 2 left, find the lowest decimal and give the other two one vote each

            # Get the lowest decimal
            lowestDec = min(decimals)

            # Get a list of indexes that match
            lowest = []
            for i in range(3):
                if decimals[i] == lowestDec:
                    lowest.append(i)

            # Add 1 vote for each that don't match
            for i in range(3):
                if i != lowest[0]:
                    totalVotes[i] += 1

            # Handle ties by voting present
            if len(lowest) > 1:
                n = len(lowest) - 1
                totalVotes[1] += n
        elif npcsLeft == 1:
            # If there's only 1 left, find the highest decimal and give the vote to it

            # Get the highest decimal
            highestDec = max(decimals)

            # Get a list of indexes that match
            highest = []
            for i in range(3):
                if decimals[i] == highestDec:
                    highest.append(i)

            if len(highest) == 1:
                # Give them the vote
                totalVotes[highest[0]] += 1
            else:
                # Handle ties by voting present
                totalVotes[1] += 1
        else:
            # There should never be more than 3 left, so give an error
            print('Error: more than 3 left')

    # Return the votes
    return totalVotes

async def getBP(replyTo):
    # Load BP
    basePartisanship = {}

    if os.path.isfile('base_partisanship.csv'):
        file = open('base_partisanship.csv', 'r')
        reader = csv.reader(file)
        lines = [row for row in reader]

        for i in range(len(lines[0])):
            if i > 0:
                for line in lines[1:]:
                    if not line[0] in basePartisanship:
                        basePartisanship[line[0]] = {}

                    basePartisanship[line[0]][lines[0][i]] = float(line[i])
    else:
        print('Error: please create base_partisanship.csv!')
        return

    # Apply randomness
    randomized = {}

    for state in basePartisanship.keys():
        randomized[state] = {}
        for party in basePartisanship[state].keys():
            value = basePartisanship[state][party]
            randomized[state][party] = random.gauss(value, 0.03 * value)

    # Normalize each state
    normalized = {}
    for state in randomized.keys():
        normalized[state] = {}
        total = 0

        for value in randomized[state].values():
            total += value

        for party in randomized[state].keys():
            normalized[state][party] = randomized[state][party] / total

    # Get the text to save
    text = 'STATE,'

    for party in normalized[list(normalized.keys())[0]].keys():
        text += '{},'.format(party)

    text = text[:-1]
    text += '\n'

    for state in normalized.keys():
        text += '{},'.format(state)

        for party in normalized[state].keys():
            text += '{},'.format(normalized[state][party])

        text = text[:-1]
        text += '\n'

    with open('new_bp.csv', 'w') as f:
        f.write(text)

    #print(message)
    #return

    # Send the message
    #resultsChannel = client.get_channel(ELECTION_RESULTS_CHANNEL)
    #await resultsChannel.send(message)

    await replyTo.reply(file=discord.File('new_bp.csv'))

@client.event
async def on_ready():
    # Tell us when the bot is online
    print(f'{client.user} is online!')
    
    # Start the hourly loop
    hourly.start()

# Main entry point
def main():
    client.run(token=TOKEN)

if __name__ == '__main__':
    main()
