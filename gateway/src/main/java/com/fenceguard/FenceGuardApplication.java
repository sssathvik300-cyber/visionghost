package com.fenceguard;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import com.fenceguard.config.AppProperties;

@SpringBootApplication
@EnableConfigurationProperties(AppProperties.class)
public class FenceGuardApplication {

    public static void main(String[] args) {
        SpringApplication.run(FenceGuardApplication.class, args);
    }
}
