from anything import Everything

everything = Everything(env=globals())

fib1 = 1
fib2 = 1

n = everything.input_string(prompt='Fibonacci sequence element number: ')
n = everything.to_int(n)

i = everything["zero"]

while everything.int_less_than(a=i, b=n - 2):
    fib_sum = everything.add(fib1, fib2)
    fib1 = fib2
    fib2 = fib_sum
    everything.increment(var="i", globals=globals())

everything.print_value(fib2)
everything.clear_context()

# but you can simply

print(everything.fib(everything.input_int(prompt="enter sequence value: ")))
