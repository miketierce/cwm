# Transcript

**0:00** Hey, I'm Dave. Welcome to my shop. Now,

**0:02** if you've ever wondered what it actually looks like when somebody trains a neural network, and I don't mean the slick animations or the conference slides, but the real thing, then stick around

**0:11** because today I'm going to show you exactly how it's done. Except we're not doing it on some rented cloud cluster with a thousand GPUs and a power bill that could light a small city. That's

**0:19** because we're going to fire up my genuine 1979 PDP144, the Big Iron,

**0:24** complete with enough blinking lights to make Waffer nervous. It's got one CPU core screaming at about 6 MHz and all the RAM you can eat, 64K at a time. And

**0:32** here's what makes this different. You're going to see what learning actually looks like once you strip away the massive data sets, the hype, and the industrial scaffolding. Just the

**0:40** essential machinery running on hardware older than most of the people online arguing about AGI. Today, you get to watch how the sausage is really made.

**0:48** Because here's the dirty little secret about neural networks. The core idea is not magical. It isn't even especially new. What's new is the scale at which

**0:57** it's being done. What's new is that we now pour enough silicon, bandwidth, and electricity into the idea to make it look like absolute sorcery from the

**1:04** outside. But underneath all of that, the machine is still doing the same basic things it was doing decades ago. Making a guess, measuring how wrong it was,

**1:12** nudging a pile of numbers in some direction, then repeating and trying again. It's less like summoning intelligence and more like training a dog, except the dog is made of matrices.

**1:21** You can show the dog an example, make it have a guess on its own, and you tell it wrong and how wrong, and then you gently tug on the leash in the right direction.

**1:29** Do this thousands of times, and eventually the dog will learn the trick.

**1:32** But you get to tug too hard, which would be akin to setting your learning rate too high, and the dog will overshoot and get nervous and spin in circles or completely forget what it was doing. Get

**1:41** it too weak and you'll still be standing there next Tuesday waiting for it to sit. Now, the repository we're building around today called Attention 11 is a

**1:49** single layer single-head transformer written in raw dog PDP11 assembly language by Damian Buret. Not Python,

**1:56** not PyTorch, not even CUDA, actual assembly language for a deck mini computer lineage that predates most of the people that are actually watching this video. Well, some of the people.

**2:06** Now, the stated goal of the model is beautifully modest and therefore technically perfect for us. Just learn how to reverse a sequence of eight digits. Not write poetry, not generate

**2:15** anime girlfriends, not replace your accountant. Just take something like 4749635 and then learn to confidently emit 56369474.

**2:26** And that tiny little task turns out to contain nearly the whole soul of the transformer story. Now, that might sound almost too cute to be interesting, but this is where the trap door opens.

**2:36** Because doing a string reversal is not actually trivial. The model can't just memorize a handful of patterns if the training is being done properly. It must

**2:44** learn a structural rule. The output token at position zero depends on the input token at position 7 and the output at position one depends on the input position six and so on. In other words,

**2:54** the network must discover a routing rule based on position rather than the content. It must actually look past what the numbers are and start to internalize

**3:02** where they go. And that's exactly the kind of thing that self attention was born to do. So what looks like a toy problem is actually a microscope slide

**3:10** with the essential biology of a transformer smeared across it. Now transformers and attention are where a lot of people start to glaze over because to be honest most of the

**3:18** explanations are pretty handwavy and full of math. So let me give you a concrete example and then my best little explanation. Let's say you're feeding

**3:26** tokens into an LLM and the sentence is Mary went down to the bank to get some blank. The interesting part is that bank is one of those words with a split

**3:34** personality. It might mean a financial institution or it might mean the side of a river. Older neural nets could sometimes sort that out, but they tended

**3:42** to process language a bit like a guy trying to remember the start of a good story while somebody else kept talking over top of them. Transformers change

**3:49** that with self attention. Each token can look back across the earlier tokens and ask in effect what else in here actually matters to me. So if the full sentence

**3:58** is Mary went down to the bank to get some cash, the model uses cash as a very strong clue for how to interpret bank.

**4:05** It's not that the words are permanently wired together. It's that attention lets the model dynamically put more weight on the parts of the context that help resolve the meaning in that particular

**4:13** place. And that turned out to be a huge deal because so much of language boils down to exactly that kind of relationship. This word changes the

**4:21** meaning of that one. And the transformer, at least from the 30,000 ft level, is just a kind of neural network that turned out to be uncannily good at

**4:28** figuring out which parts of an input matter to which other parts. Before Transformers, a lot of sequence models worked more like a guy trying to observe a landscape through a paper towel tube.

**4:38** They'd process things one bit at a time,

**4:40** trying to remember where things were relative to one another and assembling the whole thing in the scene by memory.

**4:45** Transformers changed that by letting every token look around and at the others and effectively ask, "Who else in here matters to me right now?" And that

**4:52** simple idea, attention turned out to be dynamite. Suddenly, the machine wasn't just trudging left to right, clutching a fading memory of what it had seen

**5:00** earlier. It could directly connect this word to that word, this output to that input, and this idea to that other idea several positions away. And that's why transformers became such a big deal.

**5:10** They were better at translation, better at language modeling, and eventually good at far more than text because an awful lot of intelligence ultimately boils down to understanding

**5:18** relationships. The landmark paper that kicked off the revolution was called Attention Is All You Need, which is perhaps a little smug sounding until you

**5:25** realize they might have actually been right. Once people saw how well this approach scaled, the entire AI industry basically climbed in, slammed the door,

**5:32** and said, "Let's go." Now, our little PDP11 AI isn't dealing with words. Our tokens are numbers, and the architecture here is delightfully lean. For the AI

**5:41** nerds in the audience, our tokens go into an embedding layer and then through self attention, then a residual connection, then back out through a projection and softmax into predictions.

**5:50** Just one layer, one head, a model dimension of 16, sequence length of eight, vocabulary is 10 digits. So,

**5:57** total parameter count 1,216.

**6:00** That's not a typo. 1216 parameters. You could lose that behind the couch cushions of any modern LLM and never find it again. And yet, it is a genuine

**6:09** transformer in the meaningful sense. It uses a learned token embedded, learned position embeddings, product attention,

**6:16** and a softmax output distribution. It just leaves out the extra cathedral scaffolding because for this task, the little chapel is enough. Now, if you've

**6:23** watched enough AI content, you could be forgiven for thinking that training a neural network does require a warehouse full of GPUs, an industrial cooling plant, an electrical substation of its

**6:32** own, and so on. There's always somebody in a black hoodie standing in front of a rack of servers talking about hundreds of billions of parameters and enough interconnect bandwidth to liquefy a

**6:40** lesser civilization. But what those demos rarely show you is that the underlying mathematics is actually quite frugal. The challenge has never been whether learning requires gigantic

**6:49** hardware. The challenge is whether your hardware can execute enough multiply accumulate operations, preserve enough numeric precision, and store enough

**6:57** state to make good progress before the peak death of the universe. And that's where the PDP11 becomes more than just a stunt. The attention 11 project started from an earlier fortron implementation.

**7:07** And in that form, it was simply too slow. With a uniform learning rate of 01, 100 training steps took about 25

**7:14** minutes. Reaching full accuracy would have taken about 1,500 steps. on the real period hardware. That translates to something like six and a half hours of

**7:22** training which may not sound terrible until remember these machines were very expensive, often shared and not exactly sitting around waiting to optimize your

**7:30** vanity experiment. So the author in this case did what people used to do when the hardware said no. He got serious in the old school way that I've been talking about for the last few episodes.

**7:39** Actually, he got more than serious. He went medieval on it and rewrote the whole thing in pure PDP11 assembly. And along with that came a fixed point

**7:46** neural network stack called NN11. It's one of my favorite parts of this entire project because it is exactly the kind of engineering movie you would make when

**7:54** you truly understand both the algorithm and the machine. Now floating point would be nice and I even have a floatingoint complex for my CPU. But his code is fully integer for performance.

**8:04** And I'm sure that a modern adaptive optimizer would be nice. A giant numerical library would be nice. But nice is not the same as possible or

**8:12** practical. And these machines are brutally honest about the difference. So instead, the arithmetic is tailored to the passes. The forward pass uses Q8

**8:20** fixed point or eight fractional bits and the backward pass uses 15 fractional bits for high gradient precision. And the weight accumulators live in 32-bit

**8:29** 16x6 fixed point. That pairing is clever in a way that will make systems people smile. You multiply an 8-bit fraction activation by a 15- bit fraction

**8:37** gradient and you get a 23-bit intermediate that drops perfectly into the PDP11's 32-bit register pair. Then a single arithmetic shift brings it right back to Q15. Same basic multiply cost,

**8:49** but vastly better gradient precision.

**8:51** That's not just an optimization. It's more like an arranged marriage between the math and the hardware. Now, before we run it, let me answer the one

**8:58** question that this episode really has to answer. When you train a model on a computer this simple, what is actually happening under the covers? Well, at its

**9:06** core, a neural network is just a big table of numbers sitting in memory.

**9:10** Those numbers are called weights, and they determine how strongly one node in the model influences another. In our case, if we wanted to cheat, we could

**9:17** simply wire it by hand so that the first output position listens to the last input digits, and the second output listens to the second to last input and so on. And that would give us a reversal

**9:26** machine instantly. But the whole point of training is that we do not tell the model that rule directly. We just show it lots of examples and let it gradually

**9:33** discover the pattern for itself. When we run the forward pass, we're feeding the eight digits into the model and letting the numbers flow through it. Each node

**9:41** in the network receives values from earlier nodes, multiplies each one by its corresponding weight, and then adds the results together. And that produces

**9:49** a score for that node. You can think of each little node as a little clerk at a desk. A bunch of weighted signals come in and the clerk totals them up and then

**9:57** decides what value to pass along to the next stage. That deciding what to pass along part is called the activation function. It's just a rule that says

**10:06** given this total score, what output value should this node produce? In our tiny transformer, most of those steps are fairly tame and are just part of the

**10:14** normal attention calculations. But at the very end, there was one especially important activation called softmax.

**10:20** Softmax takes the final raw scores for each possible digits 0 through nine and turns them into possibilities that add up to 100%. So instead of the model

**10:29** saying here are 10 arbitrary scores, it says something more meaningful like for output position three, I'm 92% sure that

**10:36** the right digit is five. I'm 7% sure that it's four and essentially zero for the rest. And once the model has made its guess, we can compare that guess to

**10:44** the correct reversed sequence. that gives us a measure of how wrong it was and we call that the loss. Then comes the backward pass or back propagation

**10:53** and this is the clever part of modern AI. The program works backward through that same network and figures out for each individual weight how much it

**11:01** contributed to the mistake or the error or the loss. And that produces a gradient which is basically a tiny instruction telling each weight which

**11:09** way to move if we want the answer to be a little less wrong next time. Then we update the weights. Each one gets nudged by a small amount based on its gradient

**11:18** and the current learning rate. After that, we do the whole thing again.

**11:21** Forward pass, measure the loss, backward pass, update the weights over and over on many examples. And that repetition is

**11:28** what training really is. Every cycle slightly reshapes the big table of numbers in memory. After enough passes,

**11:34** the model starts producing the right answers consistently on its own. And that's why so many training samples are desirable, because each pass changes the

**11:42** weights by only a tiny amount. So long-term trends and intelligence only emerge after it has been trained on many many examples. And yet it hasn't learned

**11:51** anything in a mystical sense. It has simply adjusted its internal connection strengths until the math flowing through the network now just happens to

**11:58** implement the reversal rule. In this tiny transformer, that rule ends up being carried mostly by the attention mechanism. The model gradually learns

**12:06** which input positions should matter to which output positions. Position zero learns to pay strong attention to input position 7. position one to input

**12:14** position six and so on. But nobody hard-coded that mapping. It all emerges from those repeated corrections. And that's the whole trick. There's no

**12:21** sorcery, just repeated error correction on a pile of adjustable numbers in memory, which is exactly the sort of brute force optimization that computers

**12:29** have always been good at. Now, I've got a real PDP1 1134 that we could run it on, but they've already done that. So,

**12:34** let's step up the deck food chain a bit by going all the way up to my big 1144.

**12:39** The PDP1 1144 was essentially Deck's cost reduced take on the mighty 1170, so you still get a lot of big system vibe without quite as much corporate

**12:47** bloodshed on the purchase order. Mine is equipped with the maximum 4 megabytes of RAM. It's got the floatingpoint complex,

**12:54** a dual hexar deuna Ethernet adapter that connects it to the internet, and a dual hex UDA50 SDI disc controller that drives four huge RA series discs. So,

**13:05** while this is absolutely a museum piece,

**13:06** it is a museum piece with enough hardware hanging off it to still look like it has opinions about your uptime.

**13:11** And while I'm narrating this part, I'll be rolling B-roll of the machine itself because frankly, if you've got an 1144 sitting there with blinking lights and drive packs the size of carry-on luggage

**13:20** and washing machines, you don't hide that off camera. Now, this machine has something that my 1134 does not, which is a cachboard in the CPU complex. It's

**13:29** worth about a 75% speed increase in dense cases, so I'm curious to see if it can shave some time off the training.

**13:35** The project requires a physical PDP11 with the extended instruction set and 32K of core or MOSS memory. The 1144

**13:43** easily clears that bar, meaning the fun part isn't can it run it, but what does it feel like to watch a transformer learn on hardware that belongs in a

**13:50** museum, but still has more front panel drama than most of modern computing. And that feeling is the whole point to this.

**13:56** But now I don't have a paper tape puncher reader. So how do we get it into memory without manually typing it all into the monitor? I decided to use another Yorg hop PDP innovation, the

**14:05** Unibone. It's a quad card that plugs right into the Unibus of the PDP1 1144.

**14:10** And one of its many party tricks is being able to load a deck paper tape image directly into RAM. So I did precisely that and then I just had to

**14:17** type S1000 to fire off execution and it sprang to life. on screen or on paper on the deck writer if you prefer. We get

**14:24** some model specs like the parameter count and the math sizes and then a report that builds as it displays statistics every 50 steps. It looks like

**14:32** loss peaks at almost three around step number 150 and then falls off rapidly as the model learns better to predict where a digit is supposed to go. By step 350,

**14:41** the model has stabilized around perfect accuracy. We could in theory continue training indefinitely and the loss would asmtoically approach but never get to

**14:48** zero. The reality is though that once the accuracy hits 100% that's all you care. There's no more point in trying to be more right than correct because once

**14:56** it works it works perfectly every time and the result is outrageous in the best possible way. The optimized model converges in about 350 training steps.

**15:05** Now on the original 34 it took almost 6 minutes but our 44 has a bit more horsepower bringing total training time down to just about 3 and 1/2 minutes.

**15:14** All in a machine family born when disco was still considered a survivable condition. The program fits in 32 kilobytes of memory and the final binary

**15:22** itself is just 6,179 bytes. That's not even a file header anymore by modern standards. That's like a rounding air wearing a fake mustache.

**15:30** When you train a model on a modern system, you rarely see any of that training. Not really. You might see a progress bar or maybe a tensorboard plot

**15:38** or if you're doing it yourself, maybe some log scrolling by like the matrix have an attacks on it. But the actual work is buried under layers of

**15:45** abstraction normally so deep that the physical reality disappears. But here,

**15:49** by contrast, the machine is naked. You can hear it, you can watch it, you can literally see the state of computation breathing through a front panel designed in an era when computers still had the

**15:58** decency to perform in public. Each weight update feels less like a hidden software event and more like some tiny industrial process taking place inside

**16:06** of a very obedient steel box. And that matters because now you know what that process actually is. It's not AI magic.

**16:13** It is the machine repeatedly updating the strength of thousands of little weighted links so that the next answer will be slightly less wrong than the last one. It's that moment when the

**16:21** original random wiring becomes a working reversal machine that I wanted you to see. That's the moment that Dr.

**16:26** Frankenstein realizes that the monster is alive. Because once you understand that, the PDP11 part becomes even cooler. This old machine is not thinking

**16:34** in some mystical sense. It's just grinding through arithmetic to update a few thousand carefully stored numbers.

**16:39** And that's the whole game. The glamour of modern AI mostly comes from doing that on a staggering scale. But the essential act of learning is already

**16:47** here fully in miniature. If I throw up some of the actual assembly language code, at least for some of you out there, you're not looking at just mysterious AI spellbooks. You're looking

**16:55** at code that loads fixed point values from memory, multiplies them,

**16:58** accumulates partial sums, stores activations, computes errors, and then walks back through the ways to update them. In higher level languages, you'd

**17:06** hide that behind layers of libraries and function calls. Here it's all laid bare.

**17:11** Move data, multiply numbers, add them up, shift to keep the fixed point in the right place, store the result, repeat.

**17:16** So when you see a little block of macro 11 on screen, the code is not the intelligence. It's just the code that repeatedly adjusts the thousands of

**17:24** numeric dials that become the learned behavior. The code itself has no intelligence, but it contains the steps necessary to create intelligence from

**17:31** whole cloth. There's also a lesson here for modern software people. And you knew I was going to say that because I can't resist it. Constraints are not the enemy

**17:40** of engineering. Constraints are what force creative engineering to happen.

**17:44** When you can't just throw the atom optimizer at the problem because with triple parameter state memory and add expensive square roots and divisions,

**17:51** you learn to think harder about step sizes. When you can't afford lavish numerical precision everywhere, you learn where and how much precision

**17:58** actually matters. When 32K is a real wall and not just a nostalgia themed wallpaper, your abstractions stop daydreaming and they start earning rent.

**18:07** Old systems are merciless that way, but they're also honest. They turn performance from an aesthetic preference into a survival trait. And maybe that's part of what makes this whole

**18:15** demonstration so educational. It doesn't just teach you what a transformer is. It reminds you what a computer is. Because a computer is not a wish-ranting device.

**18:23** It is a machine with specific strengths and weaknesses. Neural networks are often presented as though they live in some ethereal mathematical realm. But

**18:31** they do not. They live in memory layouts, data representations, instruction timings, cache behavior,

**18:36** register wids, and all the little grubby realities of implementation. The miracle is never that the equations exist. The miracle is that you can persuade actual

**18:45** hardware to carry them out efficiently enough to learn something useful before humans wander off for coffee and never come back or the heat death. I'm not sure which I'm going to go with there.

**18:53** Now, I have no way to know for sure, but I suspect the engineering teams at OpenAI, Anthropic, XAI, and Google are all paying attention to training

**19:00** performance and hardware constraints in a way that they haven't for a long time.

**19:04** Because in today's market, finishing training 30% sooner is a significant competitive advantage. Being able to do it with less hardware is a capital cost

**19:12** advantage. And of course, they're very concerned with reducing power consumption at the same time. And so,

**19:16** the incentives are all aligned towards efficiency. We may not have yet run the course of just throwing more GPUs at the problem, but we will soon enough. And

**19:24** when we do, efficiency and optimization will become a durable competitive advantage for anybody who practices them. That's why I find this more

**19:32** inspiring than yet another AI demo where somebody generates a watercolor astronaut riding a copy bar through Venice on his Mac Mini. Those are fun,

**19:39** sure, but this is closer to the root of the tree. This is one person taking a class of algorithms that the world currently treats like sacred fire and

**19:47** proving that at least their essence can be reduced, understood, implemented, and trained on a machine old enough to remember when software came with toggle switches and three- ring binders. And

**19:55** maybe that makes me a bit like that weird keeper dude from the movie Quest for Fire, where I've got the last spark of what remains of our connection from AI back to the physical computer. And if

**20:04** you're wondering whether this somehow diminishes modern AI, I'd actually say the opposite. To me, it enhances it.

**20:10** reminds us that there is continuity here. The transformer is not an alien technology that appeared in a white paper by immaculate conception. It's part of a long engineering lineage.

**20:19** Linear algebra, optimization, attention representation, precision management,

**20:24** data flow, hardware awareness, all of these ideas connect. Seeing them run on a PDP11 is a bit like hearing a symphony played live on old instruments. The

**20:32** notes are recognizably the same, but now you can hear the construction of the thing. So today, when we loaded this code into the 1144 and let it start chewing through the training steps, what

**20:41** we were really watching was not just a vintage computer doing a party trick.

**20:45** We're watching the stripped down anatomy of learning itself. The model begins dumb. The loss begins high. Accuracy stumbles around like a man trying to

**20:52** assemble IKEA furniture in the back of a moving van. And then somewhere along the way, the weights settle into a pattern.

**20:58** And the attention discovers the reversal map. And the machine crosses that invisible line from guessing into knowing. I've seen the same pattern repeat itself with my Tempest AI a

**21:06** thousand times. That is the inflection point that I wanted you to see because once you've seen it on a machine like this, you're never going to quite look at modern AI progress bars the same way again. And maybe that's the real hook.

**21:17** Not that a PDP11 can train a neural network, although that's gloriously absurd and therefore like catnip to people like me. But the deeper hook is probably that intelligence, or at least

**21:26** the sliver of machine learned competence, is a lot less mystical and a lot more mechanical than current culture tends to admit. It's made up of

**21:33** representation, routing, arithmetic, and correction. It can be explained. It can be observed. It can be debugged. It can even be coaxed into existence on a

**21:41** machine that most people would mistake for a prop from a Cold War thriller.

**21:45** After all, if it can run on my old PDP11, just how magical can it be? Which I have to admit makes the whole thing that much cooler. And hey, remember that

**21:53** if you leave a comment ending in a question mark on the video, your odds are pretty good that we'll answer it on the Dave's Attic podcast every Friday.

**22:00** Check out an episode at the link I'll throw up here on the screen. And if you enjoy it, please share it with a friend.

**22:05** If you found today's episode interesting or entertaining, remember that I'm mostly in this for the subs and likes.

**22:10** So, I'd be honored if you would consider leaving me one of each before you go today. In the meantime, and in between time, I hope to see you next time right here in Dave's Garage.

**22:18** Do it. Do it. Do it.
