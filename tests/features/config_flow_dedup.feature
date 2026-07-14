# -*- coding: utf-8 -*-
Feature: 설정 흐름의 계정 중복 방지
  같은 LG 계정으로 통합구성요소를 실수로 두 번 설정하면 기기와
  엔티티가 통째로 중복 생성된다. wideq 로그인이 성공한 시점에
  사용자명을 고유 ID로 등록해서, 이미 등록된 계정이면 중단해야 한다.

  Scenario: wideq 로그인 성공 시 사용자명(소문자/trim)으로 고유 ID가 등록된다
    When wideq 로그인이 "User@Example.com "으로 성공한다
    Then 고유 ID는 "user@example.com"으로 설정되어야 한다
    And 이미 등록된 계정인지 확인 절차가 실행되어야 한다
