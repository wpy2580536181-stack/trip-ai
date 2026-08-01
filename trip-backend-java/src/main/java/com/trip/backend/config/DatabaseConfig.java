package com.trip.backend.config;

import com.zaxxer.hikari.HikariDataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;
import org.springframework.boot.autoconfigure.orm.jpa.HibernatePropertiesCustomizer;
import org.springframework.orm.jpa.JpaTransactionManager;
import org.springframework.orm.jpa.LocalContainerEntityManagerFactoryBean;
import org.springframework.orm.jpa.vendor.HibernateJpaVendorAdapter;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

import javax.sql.DataSource;
import java.util.HashMap;

/**
 * 数据库配置（对应 Python config/database.py）
 * - HikariCP 连接池（maximum-pool-size=10）
 * - ddl-auto=none（绝不自动改表）
 * - JdbcTemplate（向量/全文/聚合原生 SQL）
 */
@Configuration
@EnableJpaRepositories(basePackages = "com.trip.backend.domain.repository")
@EnableTransactionManagement
public class DatabaseConfig {

    @Bean
    public DataSource dataSource(org.springframework.boot.jdbc.DataSourceProperties props) {
        HikariDataSource dataSource = new HikariDataSource();
        dataSource.setJdbcUrl(props.getUrl());
        dataSource.setUsername(props.getUsername());
        dataSource.setPassword(props.getPassword());
        dataSource.setDriverClassName(props.getDriverClassName());
        // 连接池配置
        dataSource.setMaximumPoolSize(10);
        dataSource.setMinimumIdle(5);
        dataSource.setConnectionTimeout(30000);
        dataSource.setIdleTimeout(600000);
        dataSource.setMaxLifetime(1800000);
        return dataSource;
    }

    @Bean
    public LocalContainerEntityManagerFactoryBean entityManagerFactory(DataSource dataSource) {
        LocalContainerEntityManagerFactoryBean emf = new LocalContainerEntityManagerFactoryBean();
        emf.setDataSource(dataSource);
        emf.setPackagesToScan("com.trip.backend.domain.entity");
        emf.setJpaVendorAdapter(new HibernateJpaVendorAdapter());

        HashMap<String, Object> jpaProps = new HashMap<>();
        jpaProps.put("hibernate.hbm2ddl.auto", "none"); // 绝不自动改表
        jpaProps.put("hibernate.show_sql", false);
        jpaProps.put("hibernate.format_sql", true);
        jpaProps.put("hibernate.dialect", "org.hibernate.dialect.PostgreSQLDialect");
        jpaProps.put("hibernate.jdbc.lob.non_contextual_creation", true);
        emf.setJpaPropertyMap(jpaProps);

        return emf;
    }

    @Bean
    public PlatformTransactionManager transactionManager(
            LocalContainerEntityManagerFactoryBean emf) {
        JpaTransactionManager tm = new JpaTransactionManager();
        tm.setEntityManagerFactory(emf.getObject());
        return tm;
    }

    @Bean
    public JdbcTemplate jdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }

    /**
     * Hibernate 属性自定义
     */
    @Bean
    public HibernatePropertiesCustomizer hibernatePropertiesCustomizer() {
        return hibernateProperties -> {
            // 连接池参数已在 DataSource 配置
        };
    }
}
