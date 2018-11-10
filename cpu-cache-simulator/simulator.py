import argparse
import random
import util
from cache import Cache
from memory import Memory
import logging
try:
    import gnureadline as readline
except ImportError:
    import readline

class SimpleCompleter(object):

    def __init__(self, options):
        self.options = sorted(options)
        return

    def complete(self, text, state):
        response = None
        if state == 0:
            # This is the first time for this text, so build a match list.
            if text:
                self.matches = [s
                                for s in self.options
                                if s and s.startswith(text)]
                logging.debug('%s matches: %s', repr(text), self.matches)
            else:
                self.matches = self.options[:]
                logging.debug('(empty input) matches: %s', self.matches)

        # Return the state'th item from the match list,
        # if we have that many.
        try:
            response = self.matches[state]
        except IndexError:
            response = None
        logging.debug('complete(%s, %s) => %s',
                      repr(text), state, repr(response))
        return response

def read(address, memory, cache):
    """Read a byte from cache."""
    cache_block = cache.read(address)

    if cache_block:
        global hits
        hits += 1
    else:
        block = memory.get_block(address)
        victim_info = cache.load(address, block)
        cache_block = cache.read(address)

        global misses
        misses += 1

        # Write victim line's block to memory if replaced
        if victim_info:
            memory.set_block(victim_info[0], victim_info[1])

    return cache_block[cache.get_offset(address)]


def write(address, byte, memory, cache):
    """Write a byte to cache."""
    written = cache.write(address, byte)

    if written:
        global hits
        hits += 1
    else:
        global misses
        misses += 1

    if args.WRITE == Cache.WRITE_THROUGH:
        # Write block to memory
        block = memory.get_block(address)
        block[cache.get_offset(address)] = byte
        memory.set_block(address, block)
    elif args.WRITE == Cache.WRITE_BACK:
        if not written:
            # Write block to cache
            block = memory.get_block(address)
            cache.load(address, block)
            cache.write(address, byte)

replacement_policies = ["LRU", "LFU", "FIFO", "RAND"]
write_policies = ["WB", "WT"]

parser = argparse.ArgumentParser(description="Simulate the cache of a CPU.")

parser.add_argument("MEMORY", metavar="MEMORY", type=int,
                    help="Size of main memory in 2^N bytes")
parser.add_argument("CACHE", metavar="CACHE", type=int,
                    help="Size of the cache in 2^N bytes")
parser.add_argument("BLOCK", metavar="BLOCK", type=int,
                    help="Size of a block of memory in 2^N bytes")
parser.add_argument("MAPPING", metavar="MAPPING", type=int,
                    help="Mapping policy for cache in 2^N ways")
parser.add_argument("REPLACE", metavar="REPLACE", choices=replacement_policies,
                    help="Replacement policy for cache {"+", ".join(replacement_policies)+"}")
parser.add_argument("WRITE", metavar="WRITE", choices=write_policies,
                    help="Write policy for cache {"+", ".join(write_policies)+"}")

args = parser.parse_args()

mem_size = 2 ** args.MEMORY
cache_size = 2 ** args.CACHE
block_size = 2 ** args.BLOCK
mapping = 2 ** args.MAPPING

hits = 0
misses = 0

memory = Memory(mem_size, block_size)
cache = Cache(cache_size, mem_size, block_size,
              mapping, args.REPLACE, args.WRITE)

mapping_str = "2^{0}-way associative".format(args.MAPPING)
print("\nMemory size: " + str(mem_size) +
      " bytes (" + str(mem_size // block_size) + " blocks)")
print("Cache size: " + str(cache_size) +
      " bytes (" + str(cache_size // block_size) + " lines)")
print("Block size: " + str(block_size) + " bytes")
print("Mapping policy: " + ("direct" if mapping == 1 else mapping_str) + "\n")


# Setup Readline for history and completion
# See: https://pymotw.com/2/readline/
#  and https://pewpewthespells.com/blog/osx_readline.html
if 'libedit' in readline.__doc__:
    # macOS
    readline.parse_and_bind("bind ^I rl_complete")
else:
    # UNIX
    readline.parse_and_bind("tab: complete")
# TODO: test windows support?
readline.set_completer(SimpleCompleter(['quit', 'read', 'write', 'randread', 'randwrite', 'printcache', 'printmem', 'stats']).complete)

# Setup simple logging
LOG_FILENAME = '.simulator.log'
logging.basicConfig(filename=LOG_FILENAME,level=logging.DEBUG)
# TODO: add logging to other methods, too

# Use raw_input instead of input if running in Python 2.7
# See: https://stackoverflow.com/questions/21731043/use-of-input-raw-input-in-python-2-and-3
if hasattr(__builtins__, 'raw_input'): input = raw_input

command = None

while (command != "quit"):
    operation = input("> ")
    operation = operation.split()

    try:
        command = operation[0]
        params = operation[1:]

        if command == "read" and len(params) == 1:
            address = int(params[0],0)
            byte = read(address, memory, cache)

            print("\nByte 0x" + util.hex_str(byte, 2) + " read from " +
                  util.bin_str(address, args.MEMORY) + "\n")

        elif command == "write" and len(params) == 2:
            address = int(params[0],0)
            byte = int(params[1],0)

            write(address, byte, memory, cache)

            print("\nByte 0x" + util.hex_str(byte, 2) + " written to " +
                  util.bin_str(address, args.MEMORY) + "\n")

        elif command == "randread" and len(params) == 1:
            amount = int(params[0],0)

            for i in range(amount):
                address = random.randint(0, mem_size - 1)
                read(address, memory, cache)

            print("\n" + str(amount) + " bytes read from memory\n")

        elif command == "randwrite" and len(params) == 1:
            amount = int(params[0],0)

            for i in range(amount):
                address = random.randint(0, mem_size - 1)
                byte = util.rand_byte()
                write(address, byte, memory, cache)

            print("\n" + str(amount) + " bytes written to memory\n")

        elif command == "printcache" and len(params) == 2:
            start = int(params[0],0)
            amount = int(params[1],0)

            cache.print_section(start, amount)

        elif command == "printmem" and len(params) == 2:
            start = int(params[0],0)
            amount = int(params[1],0)

            memory.print_section(start, amount)

        elif command == "stats" and len(params) == 0:
            ratio = (hits / ((hits + misses) if misses else 1)) * 100

            print("\nHits: {0} | Misses: {1}".format(hits, misses))
            print("Hit/Miss Ratio: {0:.2f}%".format(ratio) + "\n")

        elif command != "quit":
            print("\nERROR: invalid command\n")

    except IndexError:
        print("\nERROR: out of bounds\n")
    except:
        print("\nERROR: incorrect syntax\n")
