FROM python:3.9-alpine
WORKDIR /app
COPY main1.py /app/
COPY requirements.txt /app/
COPY .env /app/
COPY creds.json /app/
RUN pip install --no-cache-dir -r requirements.txt
ENV CLICKUP_API_TOKEN pk_73223342_17LY9UC6TE84D6P5MF2ALXU5W8UT6LHA
#replace this as this is not the facets slack webhook url 
ENV SLACK_WEBHOOK_URL https://hooks.slack.com/services/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  
LABEL MAINTAINER="rauneet"
CMD [ "python","bug_reporter_main.py" ]
