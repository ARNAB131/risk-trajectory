FROM ruby:3.3

WORKDIR /app
COPY Gemfile .
RUN bundle install

COPY app.rb .

EXPOSE 4567
CMD ["ruby", "app.rb"]
