# Questions for Fair Trade USA

This is for Fair Trade USA staff at the hackathon. Each question is short and can be answered in a sentence or two. We will copy your answers into issue #38 and into the specs, so the build follows FTUSA policy rather than our guesses.

Questions are numbered so they can be referred to in a meeting ("Q4"). Where a question says "until we hear back", that is what the system does today.

A few terms:

- **Record:** the summary of a conversation that FTUSA reviewers and analysts see.
- **Conversation memory:** a copy of the conversation's messages, kept so a producer can close the browser and resume later.
- **Logs:** technical files that AWS keeps about each conversation, used by engineers to find faults.

## Consent and privacy

### Q1. If a producer leaves without answering the consent question, what should we record?

- **Why it matters:** many producers will close the browser part way through. We need to know whether that counts as "declined", as "no answer", or as nothing at all.
- **What we'll do until we hear back:** nothing built yet. No record type is defined for this case.
- **Affects:** #13, #19, #21, #26. [Conversation steps](../specs/13-conversation-steps.md), [Consent and decline](../specs/19-consent-and-decline.md), [Out of scope](../specs/21-out-of-scope.md), [Write-back](../specs/26-write-back.md)

### Q2. Can a producer withdraw consent after their record has been saved?

- **Why it matters:** producers own their data. If they can't take a summary back, we should not imply they can.
- **What we'll do until we hear back:** a producer can change their consent answer as often as they like until the conversation closes. After it closes, nothing changes from the chat, and nothing deletes records. A "your record" view is planned (#32) but not built.
- **Affects:** #19, #26, #28, #32. [Consent and decline](../specs/19-consent-and-decline.md), [Write-back](../specs/26-write-back.md), [Athena sync](../specs/28-athena-sync.md)

### Q3. What exactly does "may also be shared outward" allow?

- **Why it matters:** producers choose between "FTUSA internal only" and "also shared outward". They need to know who could see their story, and in what form, before they choose.
- **What we'll do until we hear back:** the spec describes it only as "for example, aggregated for partners". Nothing yet treats the two options differently.
- **Affects:** #19, #29. [Consent and decline](../specs/19-consent-and-decline.md)

### Q4. Is a simple button choice enough consent for Indigenous communities in the demo?

- **Why it matters:** the vision document requires Free, Prior and Informed Consent (FPIC) for Indigenous communities. The demo asks for consent with buttons only. The vision marks this simplification as our assumption, not FTUSA's decision.
- **What we'll do until we hear back:** three buttons (internal only, also shared outward, decline), the same for every producer.
- **Affects:** #19. [Consent and decline](../specs/19-consent-and-decline.md), [Vision, Journey 2](../requirements/vision.md)

## Data retention and logs

### Q5. May a producer's own words be written to the system's logs at all?

- **Why it matters:** we tested this. The AWS agent service writes the producer's full message, FEX's reply and the data FEX looked up into a log. By default that log is kept forever. A shorter technical log (kept 30 days) holds only timings and tool names, not what was said. So a producer who declines could still have their words sitting in a log.
- **What we'll do until we hear back:** before any real conversation, set the full log to delete itself after a short time (1 to 7 days) and limit who can read it. If you say "no content in logs", we will switch content logging off and test that it is really off.
- **Affects:** #4, #5, #19. [AgentCore spike findings](../adr/0002-agentcore-runtime-spike.md#do-agentcore-traces-capture-message-content-for-38-the-decline-question), [Consent and decline](../specs/19-consent-and-decline.md)

### Q6. When a producer declines, should their stored conversation be deleted straight away?

- **Why it matters:** a declined record holds no story, but the conversation memory and the logs (Q5) still hold the messages for a while. The demo currently tells a producer who declines "Nothing from this conversation will be stored". That is not fully true today.
- **What we'll do until we hear back:** the declined record has no story (the system rejects one). Conversation memory is not built yet (#59). Its plan keeps messages until they expire (Q8) and includes a function to delete one conversation's messages, but nothing calls it on a decline. We may need to change the decline message.
- **Affects:** #19, #59. [Consent and decline](../specs/19-consent-and-decline.md), [Memory](../specs/memory.md)

### Q7. How long should conversation records be kept?

- **Why it matters:** records hold producers' stories. FTUSA's privacy policy should set how long, not us.
- **What we'll do until we hear back:** records are kept with no end date. Nothing deletes them.
- **Affects:** #26, #28. [Write-back](../specs/26-write-back.md), [Athena sync](../specs/28-athena-sync.md)

### Q8. How long should conversation memory be kept?

- **Why it matters:** this is how long a producer's messages stay stored so they can resume, and how long FEX can remember earlier conversations. Longer is more convenient; shorter keeps less personal data.
- **What we'll do until we hear back:** it is a setting with no value chosen yet. AWS allows 3 to 365 days for messages. Longer-term memories are kept forever unless an expiry of at least 31 days is set. Whatever is chosen must be longer than the longest a conversation can stay open (Q12).
- **Affects:** #59. [Memory](../specs/memory.md)

## Standards (APS and FPS)

### Q9. Is FPS the "Farm Workforce" or the "Factory" Production Standard, and who does it apply to?

- **Why it matters:** the vision document says "Farm Workforce Production Standard". The workbook and PDF we have say "Factory Production Standard". If FPS only applies to factory-type producers, FEX should not cite it to farms.
- **What we'll do until we hear back:** we load FPS from the workbook as the Factory Production Standard (English only) and treat it as citable for any producer.
- **Affects:** #9, #17. [Standards loader notes](../../data/README.md)

### Q10. Which FPS criteria sheet is the official one?

- **Why it matters:** FEX cites clause numbers. If we read the wrong sheet, citations point at the wrong text.
- **What we'll do until we hear back:** we read the "Set English FPS" sheet for objectives and the "Questions English FPS" sheet for criteria, from `FPS for import 7.8.26.xlsm`.
- **Affects:** #9, #17. [Standards loader notes](../../data/README.md)

### Q11. How does a producer's `structure` (organization type) tell us their farm size: small, medium or large?

- **Why it matters:** some APS objectives differ by farm size (SF, MF, LF). Without the mapping, FEX may cite the version for the wrong size of farm.
- **What we'll do until we hear back:** each APS clause lists which farm sizes it covers, but nothing yet matches a producer to a size.
- **Affects:** #9, #14, #17. [Standards loader notes](../../data/README.md)

## Conversation behaviour

### Q12. How long can a producer leave a conversation and still come back to it?

- **Why it matters:** a producer may want to check with their committee before finishing. We need two numbers: how long a conversation can sit idle before it closes, and the longest any conversation can stay open.
- **What we'll do until we hear back:** both are settings with no value chosen yet.
- **Affects:** #13, #25, #59. [Conversation steps](../specs/13-conversation-steps.md), [Chat endpoint](../specs/25-chat-endpoint.md), [Memory](../specs/memory.md)

### Q13. What may FEX remember from a producer's earlier conversations?

- **Why it matters:** remembering saves the producer repeating themselves. But a story they declined to share must never come back later, in a new conversation or a new record.
- **What we'll do until we hear back:** nothing is built yet (#59). The plan builds this switched off, so FEX starts each new conversation knowing only the producer's record.
- **Affects:** #59, #19. [Memory](../specs/memory.md)

## Data meaning

### Q14. The survey file still has answers about harassment and discrimination, borrowing, access to medical care and children's school enrolment. Was that intended?

- **Why it matters:** the dataset note says sensitive fields were removed. These answers are sensitive, and FEX should not repeat them back or use them without FTUSA's agreement.
- **What we'll do until we hear back:** nothing built yet reads survey answers. We plan to use only farming, water and farming-practice answers.
- **Affects:** #7, #14. [Vision](../requirements/vision.md)

### Q15. Some projects start on 1 January 1970. Does that mean "start date unknown"?

- **Why it matters:** 1970 is a common placeholder for a missing date. If FEX shows it as real, a peer example would claim a project began in 1970.
- **What we'll do until we hear back:** the date is passed through as it is in the file. Nothing hides it yet.
- **Affects:** #16. [Tool contracts](tool-contracts.md)

## Wording and languages

### Q16. Is there FTUSA-approved Spanish and French wording for the consent choices?

- **Why it matters:** consent is only meaningful if the producer understands it. Wording written by engineers may not match FTUSA's legal or field language.
- **What we'll do until we hear back:** the demo uses English and Spanish text written by the team, not approved by FTUSA. French is not built yet (#24).
- **Affects:** #19, #22, #24, #30. [Consent and decline](../specs/19-consent-and-decline.md), [Spanish exchange](../specs/22-spanish-exchange.md)

## Dashboard

### Q17. For the "hide any group smaller than 5" rule, should we count distinct producers or records?

- **Why it matters:** one producer can have several records. Counting records could show a group of 5 that is really 1 or 2 producers, who could then be identified.
- **What we'll do until we hear back:** we count records. Any group of 1 to 4 records is hidden.
- **Affects:** #29, #33. [Dashboard code](../../web/src/lib/analytics.ts)

## Answered

(None yet. Move questions here with the answer, the date and who answered.)

## Team-only decisions (not for FTUSA)

These are also marked "Not decided" in the specs. They are engineering choices for the team, listed so nothing is lost.

- **How callers sign in, and the stand-in used for the demo.** [#11](../specs/11-identity.md), [#25](../specs/25-chat-endpoint.md). FTUSA may have a preference for later; for the hackathon it is our call.
- **How FEX decides a request is out of scope.** [#21](../specs/21-out-of-scope.md)
- **Node.js runtime version** (the technical environment document says Node 20, which AWS Lambda has deprecated). [#25](../specs/25-chat-endpoint.md)
- **How a record shows consent while a reopened playback waits for a new answer.** [#19](../specs/19-consent-and-decline.md), [#26](../specs/26-write-back.md)
- **Whether records of still-open conversations appear in Athena.** [#28](../specs/28-athena-sync.md). Consent can still change while a conversation is open, so check this against Q2.
- **How record deletion and the Athena resync interact,** once Q7 is answered. [#28](../specs/28-athena-sync.md)
