# hiring-assistant


1. Resume Parser Agent (Input : resume, ocrs the text, stores the details in the db, )
2. Interview taking Agent (Input : candidate resume, and related details, job listing requirements, interview starts constant streaming, and there should be another agent who keeps extracting facts from the interview process, or this cam be done post interview process as well)
3. Screener Agent (takes the interview transcript generates a matching score)
4. Chat Agent (Deep Research on the Database)
5. Job Listing parsing Agent (takes the listing as input, and then stores that listing to db)


Lets just keep one backend with apis, models, schemas and direct db access from here itself
