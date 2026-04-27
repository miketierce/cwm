# How Transistors Work & Build a Computer — CoreDumpped

---

**[0:00]** this video is sponsored by brilliant

**[0:02]** transistors are very simple components

**[0:05]** they are basically electronic switches

**[0:07]** when we apply current to one of its

**[0:09]** terminals a transistor lets electricity

**[0:11]** pass through but how can this simple

**[0:14]** Behavior make computers

**[0:15]** possible in today's video we are going

**[0:18]** to learn how transistors can be used to

**[0:20]** achieve more complex

**[0:22]** tasks like doing math and even

**[0:24]** interpreting

**[0:27]** instructions hi friends my name is

**[0:30]** George and this is core dumped before we

**[0:33]** begin just a reminder that you can find

**[0:35]** me on social media and our Discord

**[0:36]** server where I'm available to answer

**[0:38]** your questions and by the way I keep

**[0:41]** getting requests to use my own voice

**[0:42]** instead of using text to speech the

**[0:44]** reason I don't record myself is because

**[0:46]** I grew up in South America and I'm not a

**[0:48]** native English speaker so I hope you

**[0:50]** like modern family cuz once I start

**[0:52]** recording myself that's what it will

**[0:53]** sound

**[0:55]** like Anyway let's start a single

**[0:58]** transistor typically has three terminals

**[1:01]** a collector an emitter and a base in a

**[1:04]** circuit it can act as an insulator

**[1:06]** preventing electricity from flowing

**[1:07]** between the collector and emitter

**[1:09]** terminals but if we apply a small

**[1:11]** current to the base terminal it acts as

**[1:13]** a conductor allowing electricity to

**[1:16]** flow essentially a transistor can be

**[1:18]** seen as a switch but instead of

**[1:20]** mechanical movement it operates by using

**[1:22]** electrical

**[1:24]** signals in this example circuit we are

**[1:26]** using a transistor to turn on and off an

**[1:28]** LED by utilizing the base terminal as an

**[1:31]** input and the emitter terminal as an

**[1:33]** output signal we can mimic the input

**[1:36]** signal with a switch and visually

**[1:37]** represent the output signal with the

**[1:41]** LED let's dub this a simple gate in a

**[1:44]** simple gate when the input is zero the

**[1:46]** output is zero when the input is one the

**[1:49]** output is

**[1:51]** one now let's tweak things a bit here

**[1:54]** when the input is zero the LED is on due

**[1:57]** to the way it is arranged within the

**[1:58]** circuit but pay attention to this

**[2:01]** setting the input to one causes the LED

**[2:03]** to turn off indicating to us the output

**[2:06]** is a zero this setup is commonly

**[2:08]** referred to as an inverter or a not

**[2:11]** gate this may seem a bit confusing this

**[2:14]** video I found on Twitter is a perfect

**[2:16]** example of this

**[2:24]** effect and if you want more details you

**[2:26]** can watch this video by Ben eer where he

**[2:29]** explains all this using real

**[2:31]** components we're not limited to just one

**[2:34]** transistor by using multiple transistors

**[2:36]** we can achieve more complex Behavior if

**[2:39]** two transistors are connected in series

**[2:41]** when both inputs are zero the output

**[2:43]** will be zero because both transistors

**[2:45]** act as insulators similarly if either

**[2:48]** input is zero the output will be zero

**[2:52]** the only way to obtain a one in the

**[2:53]** output is by having both transistors act

**[2:55]** as conductors which happens when both

**[2:57]** inputs are set to one

**[3:00]** this is where we begin to apply a

**[3:01]** powerful concept called abstraction

**[3:04]** instead of focusing on the individual

**[3:06]** transistors in the circuit we can

**[3:07]** abstract this into a white box a box

**[3:10]** that consistently outputs a specific

**[3:12]** value based on two given

**[3:15]** inputs this is known as an and gate an

**[3:18]** and gate outputs a value of one if and

**[3:21]** only if both inputs are one otherwise

**[3:23]** the output will be

**[3:27]** zero if we connect the transistors in

**[3:29]** parallel when both transistors act as

**[3:32]** insulators electricity cannot

**[3:34]** flow but in this setup having any

**[3:37]** transistor acting as conductor is enough

**[3:39]** to allow electricity to

**[3:41]** flow so in this arrangement to get an

**[3:43]** output of one is not strictly necessary

**[3:46]** to set both inputs to

**[3:48]** one once more we can abstract this

**[3:51]** circuit into a box known as an or gate

**[3:55]** an or gate outputs a value of zero if

**[3:57]** and only if both inputs are zero

**[4:00]** otherwise it outputs a value of

**[4:03]** one these circuits known as logic gates

**[4:05]** are so fundamental that instead of

**[4:07]** representing them with boxes each one is

**[4:09]** assigned a dedicated

**[4:11]** symbol notice that since inputs and

**[4:14]** outputs are electrical signals we can

**[4:16]** connect the output of one logic gate to

**[4:18]** the input of another this allows us to

**[4:21]** combine logic gates to achieve even more

**[4:23]** complex

**[4:24]** behavior for example if we desire this

**[4:27]** particular Behavior we can combine logic

**[4:29]** G Gates accordingly to achieve

**[4:35]** it this is where we begin to see the

**[4:37]** power of abstractions while this setup

**[4:40]** is ultimately composed of transistors

**[4:42]** it's much simpler to understand what's

**[4:44]** happening by thinking in terms of logic

**[4:46]** gates this circuit is known as an xor

**[4:49]** gate and it is also very important in

**[4:51]** computer science so it has its own

**[4:54]** symbol and now that we understand what

**[4:57]** logic gates are let's use them to create

**[4:59]** more use ful things let's start with

**[5:02]** adders adding binary numbers is actually

**[5:04]** quite simple in fact binary addition

**[5:06]** works just like decimal addition 0 + 0 =

**[5:10]** 0 0 + 1 = 1 1 + 0 = 1 and 1 + 1 = two

**[5:17]** however the value two cannot be

**[5:18]** represented with a single binary digit

**[5:21]** when this occurs we say the addition has

**[5:23]** overflowed meaning we require an

**[5:25]** additional bit to represent the value so

**[5:27]** what we're aiming for is a circuit that

**[5:29]** takes two input values and produces two

**[5:31]** outputs the sum and the

**[5:34]** carry let's break down the

**[5:36]** sum but before a quick message from

**[5:39]** brilliant your learning process doesn't

**[5:42]** have to be synonymous with mindlessly

**[5:43]** scrolling through a

**[5:45]** PDF brilliant is designed to offer small

**[5:47]** lessons that you can engage with

**[5:49]** whenever you find the time making

**[5:50]** learning a little each day both

**[5:52]** enjoyable and convenient one of the best

**[5:55]** brilliant features is the interactive

**[5:56]** nature of their lessons which encourage

**[5:58]** critical thinking skills skills through

**[6:00]** problem solving activities for those

**[6:02]** aiming to enhance their problem solving

**[6:04]** abilities brilliant is an ideal platform

**[6:07]** it's latest course thinking in code lays

**[6:10]** down the foundational principles of

**[6:11]** coding enabling you to adopt the mindset

**[6:14]** of a programmer and you can pick more

**[6:16]** advanced topics such as Python

**[6:18]** Programming and the mechanics of large

**[6:20]** language models all while engaging with

**[6:22]** small and fun interactive lessons you

**[6:25]** can get for free 30 days of brilliant

**[6:27]** premium and a lifetime 20% discount when

**[6:29]** subscribing by accessing brilliant.org

**[6:31]** dumped or by using the link in the

**[6:34]** description below and now back to the

**[6:36]** video let's break down the sum we

**[6:39]** require a circuit that outputs zero when

**[6:41]** both inputs are the same and one when

**[6:43]** they differ does this sound familiar

**[6:46]** it's precisely what an exor gate

**[6:48]** accomplishes so we've already solved

**[6:50]** half of the puzzle for the carry output

**[6:53]** we need a circuit that outputs the value

**[6:55]** one only when both inputs are

**[6:57]** one this matches the behavior of and

**[7:01]** gate and there we have it we've crafted

**[7:04]** a circuit capable of adding two singled

**[7:06]** digigit binary

**[7:08]** numbers okay but what about multi-digit

**[7:10]** binary

**[7:11]** addition well let's try since we have to

**[7:15]** add numbers in each row using one Adder

**[7:17]** for each row seems logical it works well

**[7:20]** for the first row but when we move to

**[7:21]** the second row there's an

**[7:24]** issue we need to consider that the

**[7:26]** previous row might have created a carry

**[7:28]** but because the adder circuit only

**[7:29]** accepts two inputs it doesn't account

**[7:31]** for this carry because of this

**[7:34]** limitation this circuit is known as a

**[7:36]** half adder and it is not useful in this

**[7:39]** scenario what we need is a full adder a

**[7:42]** circuit that can handle not only the two

**[7:44]** bits being added but also take into

**[7:46]** account the carry from a previous

**[7:48]** addition here's the circuit we're

**[7:49]** working towards think of it as a circuit

**[7:52]** capable of adding three singled digigit

**[7:54]** binary

**[7:57]** numbers to simplify matters we can

**[8:00]** encapsulate this in a box which we'll

**[8:02]** call a full

**[8:04]** adder with full adders we can now add

**[8:07]** multi-digit binary

**[8:09]** numbers the carry output of each full

**[8:11]** adder feeds directly into the carry

**[8:12]** input of the next full adder as shown

**[8:14]** here in this

**[8:17]** animation to add binary numbers of n

**[8:19]** digits in one go n full adders are

**[8:21]** needed for example if we aim to add two

**[8:24]** 8 bit numbers we'll need eight full

**[8:27]** adders remember that values are

**[8:29]** represent Ed here using electrical

**[8:30]** signals since electricity moves at

**[8:32]** incredible speed once we alter the input

**[8:35]** the output changes almost instantly and

**[8:38]** this is what makes transistors ideal for

**[8:39]** this job while logic gates can be

**[8:42]** crafted from other components like

**[8:43]** relays and even fancy 3D printed Parts

**[8:46]** powered by weird stuff like marbles or

**[8:48]** even water none of this matches the

**[8:50]** speed and compactness of

**[8:52]** transistors before Things become overly

**[8:55]** complex we can one more time package all

**[8:57]** of this functionality into a special

**[8:59]** component known as an 8bit

**[9:01]** Adder an 8bit Adder takes two 8-bit

**[9:04]** numbers as input and produces the sum of

**[9:06]** the inputs as another 8bit number it

**[9:08]** also provides an overflow signal which

**[9:10]** is essentially the carry out output of

**[9:12]** the last full adder inside this overflow

**[9:15]** signal is crucial because it informs us

**[9:17]** whether the storage capacity being

**[9:19]** utilized is adequate to represent the

**[9:20]** result of the

**[9:22]** operation in this example both inputs

**[9:24]** are one bite long but if we attempt to

**[9:27]** store the output in just one bite we

**[9:29]** will miss information resulting in an

**[9:31]** incorrect

**[9:32]** value by monitoring the Overflow output

**[9:35]** we can recognize the need for an extra

**[9:36]** bite to accurately store the

**[9:39]** output believe it or not neglecting to

**[9:42]** manage operation overflows can lead to

**[9:44]** undefined Behavior sometimes with severe

**[9:46]** consequences like this rocket accident

**[9:48]** in

**[9:53]** 1996 and we can continue to move to

**[9:55]** higher levels of abstraction if we want

**[9:57]** to make a circuit that increments an

**[9:59]** input value we can simply use an adder

**[10:02]** and set the second input to always be

**[10:04]** one we've only talked about adders in

**[10:07]** detail but in the end it's all about

**[10:09]** logic gates with them we can make more

**[10:11]** useful things like a full subtractor

**[10:13]** that then can be used to build an 8 bit

**[10:17]** subtractor and from there we could keep

**[10:20]** going and make even more complicated

**[10:22]** stuff as you may have guessed inside the

**[10:25]** CPU there's a special component that

**[10:27]** houses all these circuits for now let's

**[10:30]** call it our mysterious

**[10:32]** component the question we want to answer

**[10:35]** now is when a CPU reads an instruction

**[10:37]** how does it identify which one of these

**[10:39]** circuits corresponds to that specific

**[10:41]** instruction how does the computer

**[10:43]** discern adding numbers upon encountering

**[10:45]** a particular instruction and subtract

**[10:47]** them upon encountering

**[10:48]** another I mean some instructions aren't

**[10:51]** even arithmetic

**[10:53]** operations the last type of component we

**[10:55]** are covering today are binary

**[10:57]** decoders let's take a look at this

**[10:59]** circuit and examine the output for every

**[11:01]** input combination the first thing we can

**[11:03]** notice here is that each combination

**[11:05]** triggers a specific output to activate

**[11:07]** while deactivating all other

**[11:10]** outputs another way to see it is that

**[11:12]** the circuit receives the binary number

**[11:14]** that corresponds to the position of the

**[11:16]** output we wish to

**[11:18]** activate this is what binary decoders do

**[11:22]** when it receives an input one and only

**[11:24]** one output has the value of one with all

**[11:26]** others outputting the value of zero

**[11:30]** if we have a decoder with three inputs

**[11:32]** we can control which of eight outputs

**[11:33]** turns

**[11:34]** on four inputs well we can control 16

**[11:38]** outputs and so

**[11:40]** on this is huge because it means that we

**[11:43]** are also capable of creating circuits

**[11:45]** that can select among multiple

**[11:48]** options now remember that assembly code

**[11:51]** is just a humanfriendly representation

**[11:52]** of machine code the actual code

**[11:55]** consisting of ones and zeros that

**[11:57]** computers comprehend

**[11:59]** not all instructions are arithmetic

**[12:01]** operations some of them are instructions

**[12:03]** dedicated to fetch and write data to

**[12:04]** memory and other stuff like that let's

**[12:07]** imagine a very basic architecture where

**[12:09]** if the first two bits of an instruction

**[12:11]** are zeros the computer interprets them

**[12:13]** as arithmetic operation

**[12:15]** instructions in this example to verify

**[12:18]** this we could employ nor Gates given the

**[12:21]** scope of this video at the moment we are

**[12:22]** not concerned with instruction that

**[12:24]** signifies something else but at least we

**[12:26]** know how to identify between them

**[12:29]** in this example architecture the third

**[12:31]** and fourth bits will determine the type

**[12:33]** of arithmetic operation to be executed

**[12:35]** for instance if those bits are 0 0 it

**[12:38]** means addition if 01 it represents

**[12:41]** subtraction and so forth this is

**[12:43]** commonly known as an OP code each op

**[12:46]** code is associated with one and only one

**[12:48]** kind of arithmetic

**[12:50]** operation when the CPU has determined

**[12:52]** that the current instruction is an

**[12:53]** arithmetic operation Our Mysterious

**[12:56]** component receives this op code and

**[12:58]** internally links those two bits to a

**[12:59]** decoder which is used to identify the

**[13:02]** desired internal

**[13:04]** operation the straightforward approach

**[13:06]** here would be by allowing all circuits

**[13:08]** to receive the inputs and generate their

**[13:10]** respective outputs but the outputs of

**[13:12]** the decoder are interconnected in a way

**[13:14]** that allows only the output of the

**[13:15]** selected operation to pass through this

**[13:20]** component keep in mind that there are

**[13:22]** more efficient ways to do this but here

**[13:24]** we focus on

**[13:25]** Simplicity Our Mysterious component can

**[13:28]** also be enclosed with within a box this

**[13:30]** is a rudimentary and somewhat incomplete

**[13:32]** version of something known as an

**[13:33]** arithmetic logic

**[13:35]** unit we'll talk about this component in

**[13:38]** more detail in a future episode where we

**[13:40]** discuss how CPUs execute instructions

**[13:42]** but beforehand an arithmetic logic unit

**[13:45]** takes input values and an OP code that

**[13:47]** tells the internal circuitry what

**[13:49]** arithmetic operation to perform between

**[13:51]** those values it then produces the result

**[13:53]** of the specified operation along with

**[13:55]** additional information such as whether

**[13:57]** the result is negative 0 or if it has

**[14:01]** overflowed and this was a very very very

**[14:03]** brief introduction to how computers use

**[14:05]** transistors to do math and follow

**[14:08]** instructions well sort of because we

**[14:10]** completely avoided an important concept

**[14:13]** memory but that's a topic for a future

**[14:15]** video so make sure to subscribe because

**[14:18]** you don't want to miss it and that's it

**[14:20]** for this episode don't forget to hit

**[14:22]** that like button if you enjoyed this

**[14:24]** video or learned something it's free and

**[14:26]** that would help me a lot
