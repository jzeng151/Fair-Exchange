Reference documents:

Design Guide: https://design.fairtradecertified.org/


Design and implement an UI in ui/sada a Django UI with no sign on and any thi ng to prototype a proof of concept of calling an API using the design guideline provided in reference.

The UI must be a winning design - base the about page with contents from: https://www.fairtradecertified.org/

The main page must be a chat interface. It will automatically make up a user and address them with fictitious name.

The chat interface is sexy and it should show chat history for:
based on profile (a) producer (b) consumer (c) Supplier.

It should show a log of inquiries and recent concerns in the region. User should have the ability to clear remove their chat. they should be able to speak their concerns using microphone. It should also be able to speak out the response. 

The chat interface should be freindly and available. We will hook it up to real API's soon. but for now just mimic the inout and output. The user interface should have an option to use a few internatioanl language; the output should also be able to translate to other languages. 

the chat should keep track and ensure guard rails that they are within boundaries.
the requirements are in: 
* /workshop/Fair-Exchange/docs/requirements/technical-environment.md
* /workshop/Fair-Exchange/docs/requirements/vision.md

make it really sexy and add documentation link.
Add a presentation page for 8 minutes demo and 2 minutes Q&A html page.
Ensure the output is suggestion and not commanding. 
the out put should show options of alternative questions and make it simple quick.

Implement what is given in: /workshop/ui/sada/SDD.md 
Use .env environment variables to use LLM.

deploy it on AWS console and give me the link to it 

Enahacements 1:
- Ability to add and attach documents, text, pictures etc.
- Show histoty of interactions based on time, week, month quarter 
- Ability to create reports based on my cht history
- Show demographis and other related concerns that are trending for the persona
- And sentiment of the response and ask some follow on questions  
- Ask for Share data permissions
- Show statistics of shared data and points earned as a part of it 

Currently system comes back as "Something went wrong" - instead makeup some real responses to mimic real response - may be even hook it up bedrock agent. and have the ability to delete the question
- starting a new chat fucntionality 