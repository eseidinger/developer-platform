FROM php:8.5.10-cli-trixie
RUN docker-php-ext-install pdo_mysql
WORKDIR /app
